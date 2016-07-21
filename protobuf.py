import cStringIO, struct

try:
    import psyco; psyco.full()
except ImportError:
    pass

class ProtoDeserializer(object):
    def __init__(self, message):
        self.sb = cStringIO.StringIO(message)
        self.bytesleft = len(message)
        
    def readsb(self, length):
        if self.bytesleft < length:
            raise Exception("DSADSDS")
        s = self.sb.read(length)
        self.bytesleft -= length
        return s
        
    def deserialize(self, want_types = False, packed = []):
        kv = {}
        while self.bytesleft > 0:
            res = self.read_varint()
            vartype, key = (res & 7), (res >> 3)
            
            if vartype == 0:
                value = self.read_varint()
            elif vartype == 1:
                value = self.read_64bit()
            elif vartype == 2:
                length = self.read_varint()
                value = self.readsb(length)
            elif vartype == 5:
                value = self.read_32bit()
            else:
                raise Exception("dSDs %d" %  vartype)
            
            if key in kv:
                if type(kv[key]) != list:
                    kv[key] = [kv[key]]
                    
                if want_types:
                    kv[key].append((vartype, value))
                else:
                    kv[key].append(value)
            else:
                if want_types:
                    kv[key] = (vartype, value)
                else:
                    kv[key] = value
            
        for key in kv:
            if key in packed and type(kv[key]) != list:
                kv[key] = [kv[key]]
                
        return kv
            
    def read_varint(self):
        val = 0
        pos = 0
        while True:
            t = ord(self.readsb(1))
            val |= (t & 0x7f) << pos
            if t & 0x80 == 0:
                return val
                
            pos += 7
        
    def read_32bit(self):
        val = self.readsb(4)
        return struct.unpack("<L", val)[0]
        
    def read_64bit(self):
        val = self.readsb(8)
        return struct.unpack("<Q", val)[0]
        
class ProtoSerializer(object):
    def __init__(self):
        self.message = ""
        
    def insert(self, key, type, value):
        self.add_varint((key << 3) | type)
        
        if type == 0:
            self.add_varint(value)
        elif type == 1:
            self.add_64int(value)
        elif type == 2:
            self.add_data(value)
        elif type == 5:
            self.add_32int(value)
        else:
            raise Exception()
            
    def insert_repeated(self, key, type, values):
        self.add_varint((key << 3) | 2)
        
        temp = ProtoBuf()
        for value in values:
            if type == 0:
                temp.add_varint(value)
            elif type == 1:
                temp.add_64int(value)
            elif type == 2:
                temp.add_data(value)
            elif type == 5:
                temp.add_32int(value)
                
        self.add_data(temp.message)
            
    
    def add_varint(self, value):
        if value < 0:
            raise Exception("negative not used yet")
            
        while value >= 0x80:
            self.message += chr(128 | (value & 0x7f))
            value >>= 7
        
        self.message += chr(value)
        
    def add_32int(self, value):
        self.message += struct.pack("<L", value)
        
    def add_64int(self, value):
        self.message += struct.pack("<Q", value)
        
    def add_data(self, data):
        self.add_varint(len(data))
        self.message += data
        
