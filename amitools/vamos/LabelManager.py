import logging
from Exceptions import InvalidMemoryAccessError
from Log import log_mem_int

MEMORY_WIDTH_BYTE = 0
MEMORY_WIDTH_WORD = 1
MEMORY_WIDTH_LONG = 2

class LabelManager:
  trace_val_str = ( "%02x      ", "%04x    ", "%08x" )
  
  def __init__(self):
    self.ranges = []
  
  def add_label(self, range):
    self.ranges.append(range)
  
  def remove_label(self, range):
    self.ranges.remove(range)
  
  def get_all_labels(self):
    return self.ranges[:]
  
  def dump(self):
    for r in self.ranges:
      print r
  
  def get_label(self, addr):
    for r in self.ranges:
      if r.is_inside(addr):
        return r
    return None

  def get_label_offset(self, addr):
    r = self.get_label(addr)
    if r == None:
      return (None, 0)
    else:
      off = addr - r.addr
      return (r, off)

  def trace_mem(self, mode, width, addr, val):
    r = self.get_label(addr)
    if r != None:
      r.trace_mem(mode, width, addr, val)
    else:
      raise InvalidMemoryAccessError(mode, width, addr, 'main')

  def _get_mem_str(self, addr):
    label = self.get_label(addr)
    if label != None:
      return "@%06x +%06x %s" % (label.addr, addr - label.addr, label.name)
    else:
      return "N/A"

  def trace_int_block(self, mode, addr, size, text="", level=logging.DEBUG, addon=""):
    log_mem_int.log(level, "%s(B): %06x: +%06x   %6s  [%s] %s", mode, addr, size, text, self._get_mem_str(addr), addon)  

  def trace_int_mem(self, mode, width, addr, value, text="", level=logging.DEBUG, addon=""):
    val = self.trace_val_str[width] % value
    log_mem_int.log(level, "%s(%d): %06x: %s  %6s  [%s] %s", mode, 2**width, addr, val, text, self._get_mem_str(addr), addon)
