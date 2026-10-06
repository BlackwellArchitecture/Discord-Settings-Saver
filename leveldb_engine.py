import os
import struct
import json
import shutil
import subprocess
import time

# --- CRC32C (Castagnoli) for LevelDB ---
def _make_crc32c_table():
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x82F63B78
            else:
                crc >>= 1
        table.append(crc)
    return table

_CRC32C_TABLE = _make_crc32c_table()

def crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for b in data:
        crc = _CRC32C_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF

def mask_crc(crc: int) -> int:
    return (((crc >> 15) | ((crc << 17) & 0xFFFFFFFF)) + 0xa282ead8) & 0xFFFFFFFF

# --- Pure Python Snappy Decompressor ---
def snappy_decompress(data: bytes) -> bytes:
    pos = 0
    length = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        length |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    
    out = bytearray()
    while pos < len(data) and len(out) < length:
        tag = data[pos]
        pos += 1
        elem_type = tag & 0x03
        if elem_type == 0:  # Literal
            lit_len = tag >> 2
            if lit_len < 60:
                lit_len += 1
            elif lit_len == 60:
                lit_len = data[pos] + 1
                pos += 1
            elif lit_len == 61:
                lit_len = struct.unpack('<H', data[pos:pos+2])[0] + 1
                pos += 2
            elif lit_len == 62:
                lit_len = struct.unpack('<I', data[pos:pos+3] + b'\x00')[0] + 1
                pos += 3
            elif lit_len == 63:
                lit_len = struct.unpack('<I', data[pos:pos+4])[0] + 1
                pos += 4
            out.extend(data[pos:pos+lit_len])
            pos += lit_len
        elif elem_type == 1:  # 1-byte offset copy
            copy_len = ((tag >> 2) & 0x07) + 4
            offset = ((tag >> 5) << 8) | data[pos]
            pos += 1
            for _ in range(copy_len):
                out.append(out[-offset])
        elif elem_type == 2:  # 2-byte offset copy
            copy_len = (tag >> 2) + 1
            offset = struct.unpack('<H', data[pos:pos+2])[0]
            pos += 2
            for _ in range(copy_len):
                out.append(out[-offset])
        elif elem_type == 3:  # 4-byte offset copy
            copy_len = (tag >> 2) + 1
            offset = struct.unpack('<I', data[pos:pos+4])[0]
            pos += 4
            for _ in range(copy_len):
                out.append(out[-offset])
    return bytes(out)

# --- Varint Helpers ---
def read_varint(buf: bytes, pos: int):
    val = 0
    shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        val |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return val, pos

def make_varint(val: int) -> bytes:
    buf = bytearray()
    while True:
        b = val & 0x7f
        val >>= 7
        if val:
            buf.append(b | 0x80)
        else:
            buf.append(b)
            break
    return bytes(buf)

# --- LevelDB Reader ---
def parse_block(data: bytes):
    if len(data) < 4:
        return
    num_restarts = struct.unpack('<I', data[-4:])[0]
    restarts_start = len(data) - 4 - 4 * num_restarts
    pos = 0
    last_key = bytearray()
    while pos < restarts_start:
        shared_len, pos = read_varint(data, pos)
        non_shared_len, pos = read_varint(data, pos)
        val_len, pos = read_varint(data, pos)
        key_delta = data[pos:pos+non_shared_len]
        pos += non_shared_len
        val = data[pos:pos+val_len]
        pos += val_len
        
        full_key = bytes(last_key[:shared_len] + key_delta)
        last_key = bytearray(full_key)
        yield full_key, val

def parse_sstable(fpath: str):
    try:
        with open(fpath, 'rb') as f:
            fdata = f.read()
    except Exception:
        return
    if len(fdata) < 48:
        return
    footer = fdata[-48:]
    if footer[-8:] != b'\x57\xfb\x80\x8b\x24\x75\x47\xdb':
        return
    pos = 0
    meta_off, pos = read_varint(footer, pos)
    meta_sz, pos = read_varint(footer, pos)
    idx_off, pos = read_varint(footer, pos)
    idx_sz, pos = read_varint(footer, pos)
    
    idx_data = fdata[idx_off:idx_off+idx_sz]
    idx_comp = fdata[idx_off+idx_sz]
    if idx_comp == 1:
        idx_data = snappy_decompress(idx_data)
    
    for key, val_handle in parse_block(idx_data):
        h_pos = 0
        b_off, h_pos = read_varint(val_handle, h_pos)
        b_sz, h_pos = read_varint(val_handle, h_pos)
        block_raw = fdata[b_off:b_off+b_sz]
        block_comp = fdata[b_off+b_sz]
        if block_comp == 1:
            block_raw = snappy_decompress(block_raw)
        for k, v in parse_block(block_raw):
            if len(k) >= 8:
                user_key = k[:-8]
                seq_type = struct.unpack('<Q', k[-8:])[0]
                seq = seq_type >> 8
                k_type = seq_type & 0xff
                yield user_key, v, seq, k_type

def parse_log(path: str):
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:
        return
    offset = 0
    while offset + 7 <= len(data):
        crc, length, rec_type = struct.unpack('<IHB', data[offset:offset+7])
        offset += 7
        if offset + length > len(data):
            break
        rec_data = data[offset:offset+length]
        offset += length
        
        if len(rec_data) >= 12:
            seq, count = struct.unpack('<QI', rec_data[:12])
            p = 12
            for i in range(count):
                if p >= len(rec_data):
                    break
                entry_type = rec_data[p]
                p += 1
                key_len = 0
                shift = 0
                while p < len(rec_data):
                    b = rec_data[p]
                    p += 1
                    key_len |= (b & 0x7f) << shift
                    if not (b & 0x80):
                        break
                    shift += 7
                key = rec_data[p:p+key_len]
                p += key_len
                
                val = b''
                if entry_type == 1: # Put
                    val_len = 0
                    shift = 0
                    while p < len(rec_data):
                        b = rec_data[p]
                        p += 1
                        val_len |= (b & 0x7f) << shift
                        if not (b & 0x80):
                            break
                        shift += 7
                    val = rec_data[p:p+val_len]
                    p += val_len
                yield key, val, seq + i, entry_type

def read_all_leveldb_records(leveldb_dir: str) -> dict[bytes, bytes]:
    """Reads all active (Put) records from a LevelDB directory."""
    records = {} # key -> (seq, val, k_type)
    if not os.path.exists(leveldb_dir):
        return {}
    
    for fname in sorted(os.listdir(leveldb_dir)):
        fpath = os.path.join(leveldb_dir, fname)
        if fname.endswith('.ldb'):
            for k, v, seq, k_type in parse_sstable(fpath):
                if k not in records or records[k][0] < seq:
                    records[k] = (seq, v, k_type)
        elif fname.endswith('.log') and os.path.getsize(fpath) > 0:
            for k, v, seq, k_type in parse_log(fpath):
                if k not in records or records[k][0] < seq:
                    records[k] = (seq, v, k_type)
                    
    live = {}
    for k, (seq, v, k_type) in records.items():
        if k_type == 1:
            live[k] = v
    return live

# --- LevelDB Writer ---
def build_sstable(kv_pairs: dict[bytes, bytes]) -> bytes:
    """Builds a complete, valid LevelDB SSTable with 0-compression blocks."""
    sorted_items = sorted(kv_pairs.items(), key=lambda x: x[0])
    if not sorted_items:
        return b''
        
    out = bytearray()
    data_block = bytearray()
    restarts = [0]
    last_key = b''
    index_records = []
    
    for user_key, val in sorted_items:
        # internal key: user_key + (seq=1 << 8 | type=1)
        internal_key = user_key + struct.pack('<Q', (1 << 8) | 1)
        shared_len = 0
        non_shared = internal_key
        
        entry = (make_varint(shared_len) + 
                 make_varint(len(non_shared)) + 
                 make_varint(len(val)) + 
                 non_shared + val)
        
        if len(data_block) + len(entry) > 4096 and len(data_block) > 0:
            restarts_bytes = bytearray()
            for r in restarts:
                restarts_bytes.extend(struct.pack('<I', r))
            restarts_bytes.extend(struct.pack('<I', len(restarts)))
            full_block = bytes(data_block + restarts_bytes)
            
            block_offset = len(out)
            block_size = len(full_block)
            comp_type = 0
            crc_val = mask_crc(crc32c(bytes([comp_type]) + full_block))
            out.extend(full_block)
            out.append(comp_type)
            out.extend(struct.pack('<I', crc_val))
            
            handle = make_varint(block_offset) + make_varint(block_size)
            index_records.append((last_key, handle))
            
            data_block = bytearray()
            restarts = [0]
            last_key = b''
            
        restarts.append(len(data_block))
        data_block.extend(entry)
        last_key = internal_key

    if len(data_block) > 0:
        restarts_bytes = bytearray()
        for r in restarts:
            restarts_bytes.extend(struct.pack('<I', r))
        restarts_bytes.extend(struct.pack('<I', len(restarts)))
        full_block = bytes(data_block + restarts_bytes)
        
        block_offset = len(out)
        block_size = len(full_block)
        comp_type = 0
        crc_val = mask_crc(crc32c(bytes([comp_type]) + full_block))
        out.extend(full_block)
        out.append(comp_type)
        out.extend(struct.pack('<I', crc_val))
        
        handle = make_varint(block_offset) + make_varint(block_size)
        index_records.append((last_key, handle))
        
    idx_block = bytearray()
    idx_restarts = [0]
    for k, h in index_records:
        entry = make_varint(0) + make_varint(len(k)) + make_varint(len(h)) + k + h
        idx_restarts.append(len(idx_block))
        idx_block.extend(entry)
    
    idx_restarts_bytes = bytearray()
    for r in idx_restarts:
        idx_restarts_bytes.extend(struct.pack('<I', r))
    idx_restarts_bytes.extend(struct.pack('<I', len(idx_restarts)))
    full_idx_block = bytes(idx_block + idx_restarts_bytes)
    
    idx_offset = len(out)
    idx_size = len(full_idx_block)
    comp_type = 0
    crc_val = mask_crc(crc32c(bytes([comp_type]) + full_idx_block))
    out.extend(full_idx_block)
    out.append(comp_type)
    out.extend(struct.pack('<I', crc_val))
    
    # Metaindex block
    meta_block = struct.pack('<II', 0, 1)
    meta_offset = len(out)
    meta_size = len(meta_block)
    crc_val = mask_crc(crc32c(bytes([0]) + meta_block))
    out.extend(meta_block)
    out.append(0)
    out.extend(struct.pack('<I', crc_val))
    
    # 48-byte Footer
    meta_handle = make_varint(meta_offset) + make_varint(meta_size)
    idx_handle = make_varint(idx_offset) + make_varint(idx_size)
    footer_content = meta_handle + idx_handle
    footer = footer_content.ljust(40, b'\x00') + b'\x57\xfb\x80\x8b\x24\x75\x47\xdb'
    out.extend(footer)
    
    return bytes(out)

def write_complete_leveldb(target_dir: str, kv_dict: dict[bytes, bytes]):
    """Writes a fresh, completely compliant LevelDB directory containing kv_dict."""
    os.makedirs(target_dir, exist_ok=True)
    
    sorted_items = sorted(kv_dict.items(), key=lambda x: x[0])
    sstable_bytes = build_sstable(kv_dict)
    
    ldb_filename = "000005.ldb"
    with open(os.path.join(target_dir, ldb_filename), 'wb') as f:
        f.write(sstable_bytes)
        
    smallest_internal = sorted_items[0][0] + struct.pack('<Q', (1 << 8) | 1)
    largest_internal = sorted_items[-1][0] + struct.pack('<Q', (1 << 8) | 1)
    
    comp_rec = b'\x01' + make_varint(len(b'leveldb.BytewiseComparator')) + b'leveldb.BytewiseComparator'
    
    edit = bytearray()
    edit.extend(b'\x02' + make_varint(6)) # log_number = 6
    edit.extend(b'\x03' + make_varint(7)) # next_file_number = 7
    edit.extend(b'\x04' + make_varint(len(kv_dict))) # last_sequence
    
    new_file_data = (
        make_varint(0) + # level 0
        make_varint(5) + # file 5
        make_varint(len(sstable_bytes)) +
        make_varint(len(smallest_internal)) + smallest_internal +
        make_varint(len(largest_internal)) + largest_internal
    )
    edit.extend(b'\x08' + new_file_data)
    
    manifest_bytes = bytearray()
    for rec in [comp_rec, bytes(edit)]:
        rec_type = 1
        crc_val = mask_crc(crc32c(bytes([rec_type]) + rec))
        manifest_bytes.extend(struct.pack('<IHB', crc_val, len(rec), rec_type) + rec)
        
    with open(os.path.join(target_dir, 'MANIFEST-000001'), 'wb') as f:
        f.write(manifest_bytes)
        
    with open(os.path.join(target_dir, 'CURRENT'), 'w') as f:
        f.write('MANIFEST-000001\n')
        
    with open(os.path.join(target_dir, '000006.log'), 'wb') as f:
        pass
        
    with open(os.path.join(target_dir, 'LOCK'), 'wb') as f:
        pass

    with open(os.path.join(target_dir, 'LOG'), 'w') as f:
        f.write("LevelDB initialized by DiscordSettingsSaver\n")
