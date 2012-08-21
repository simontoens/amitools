import time

from amitools.fs.block.Block import Block
from amitools.fs.block.UserDirBlock import UserDirBlock
from amitools.fs.block.RootBlock import RootBlock
from amitools.fs.block.FileHeaderBlock import FileHeaderBlock
from amitools.fs.block.FileListBlock import FileListBlock
from amitools.fs.block.FileDataBlock import FileDataBlock
from amitools.fs.FSString import FSString
from amitools.fs.FileName import FileName

from amitools.fs.validate.Log import Log

class BlockInfo:
  """Store essential info of a block"""
  def __init__(self, blk_num):
    self.blk_num = blk_num
    self.blk_status = BlockScan.BS_UNKNOWN
    self.blk_type = BlockScan.BT_UNKNOWN
    self.used = False
    self.own_key = None
  
  def __str__(self):
    return str(self.__dict__)

class BlockScan:
  """Scan a full volume and classify the blocks"""
  
  # block status
  BS_UNKNOWN = 0 # undecided or unchecked
  BS_READ_ERROR = 1 # error reading block
  BS_INVALID = 2 # not a detected AmigaDOS block
  BS_VALID = 3 # is a AmigaDOS block structure but type was not detected
  BS_TYPE = 4 # detected block type
  NUM_BS = 5
  
  # block type
  BT_UNKNOWN = 0
  BT_ROOT = 1
  BT_DIR = 2
  BT_FILE_HDR = 3
  BT_FILE_LIST = 4
  BT_FILE_DATA = 5
  NUM_BT = 6
  
  def __init__(self, blkdev, log):
    self.blkdev = blkdev
    self.log = log
    self.block_infos = None
    self.map_status = None
    self.map_type = None
  
  def scan(self, progress=lambda x : x):
    """Scan blocks of the given block device
       Return True if there is a chance that a file system will be found there
    """
    # range to scan
    begin_blk = self.blkdev.reserved
    num_blk = self.blkdev.num_blocks - self.blkdev.reserved
    block_infos = [None] * self.blkdev.num_blocks
    map_status = [[] for i in range(self.NUM_BS)]
    map_type = [[] for i in range(self.NUM_BT)]
    self.log.msg(Log.DEBUG,"block: checking range: +%d num=%d" % (begin_blk, num_blk))

    # scan all blocks
    last_val = 0
    last_time = int(1000 * time.clock())
    for n in range(num_blk):
      blk_num = n + begin_blk

      # update progress reporter (every 250 ms)
      val = int(n * 1000.0 / num_blk)
      now = int(1000 * time.clock())
      delta = now - last_time
      if val != last_val and delta > 250:
        progress(val)
        last_val = val
        last_time = now

      try:
        # read block from device
        blk = Block(self.blkdev, blk_num)
        blk.read()
        data = blk.data
        # create block info
        bi = BlockInfo(blk_num)
        # --- classify block ---
        if blk.valid:
          # block is valid AmigaDOS
          bi.blk_status = self.BS_VALID
          # --- root block ---
          if blk.is_root_block():
            bi.blk_type = self.BT_ROOT
            bi.blk_status = self.BS_TYPE
            root = RootBlock(self.blkdev, blk_num)
            root.set(data)
            bi.name = FSString(root.name)
            bi.hash_table = root.hash_table
            bi.parent_blk = 0
            self.log.msg(Log.INFO, "Found Root: '%s'" % bi.name, blk_num)
          # --- user dir block ---
          elif blk.is_user_dir_block():
            bi.blk_type = self.BT_DIR
            bi.blk_status = self.BS_TYPE
            user = UserDirBlock(self.blkdev, blk_num)
            user.set(data)
            bi.name = FSString(user.name)
            bi.parent_blk = user.parent
            bi.next_blk = user.hash_chain
            bi.hash_table = user.hash_table
            bi.own_key = user.own_key
            self.log.msg(Log.INFO, "Found Dir : '%s'" % bi.name, blk_num)
          # --- filter header block ---
          elif blk.is_file_header_block():
            bi.blk_type = self.BT_FILE_HDR
            bi.blk_status = self.BS_TYPE
            fh = FileHeaderBlock(self.blkdev, blk_num)
            fh.set(data)
            bi.name = FSString(fh.name)
            bi.parent_blk = fh.parent
            bi.next_blk = fh.hash_chain
            bi.own_key = fh.own_key
            self.log.msg(Log.INFO, "Found File: '%s'" % bi.name, blk_num)
          # --- file list block ---
          elif blk.is_file_list_block():
            bi.blk_type = self.BT_FILE_LIST
            fl = FileListBlock(self.blkdev, blk_num)
            fl.set(data)
            bi.blk_status = self.BS_TYPE
            bi.ext_blk = fl.extension
            bi.blk_list = fl.data_blocks
            bi.own_key = fl.own_key
          # --- file data block (OFS) ---
          elif blk.is_file_data_block():
            bi.blk_type = self.BT_FILE_DATA
            bi.blk_status = self.BS_TYPE
            fd = FileDataBlock(self.blkdev, blk_num)
            fd.set(data)
              
      except IOError,e:
        self.log.msg(Log.ERROR, "Can't read block", blk_num)
        bi = BlockInfo(blk_num)
        bi.blk_status = BS_READ_ERROR
      
      # sort in block info into array assigned by status/type
      block_infos[blk_num] = bi
      map_status[bi.blk_status].append(bi)
      map_type[bi.blk_type].append(bi)
      
      # own key ok?
      if bi.blk_status == self.BS_TYPE:
        if bi.own_key != None and bi.own_key != blk_num:
          self.log.msg(Log.ERROR, "Own key is invalid: %d type: %d" % (bi.own_key, bi.blk_type), blk_num)
        
    # first summary after block scan
    num_error_blocks = len(map_status[self.BS_READ_ERROR])
    if num_error_blocks > 0:
      self.log.msg(Log.ERROR, "%d unreadable error blocks found" % num_error_blocks)
    num_valid_blocks = len(map_status[self.BS_VALID])
    if num_valid_blocks > 0:
      self.log.msg(Log.INFO, "%d valid but unknown blocks found" % num_valid_blocks)
    num_invalid_blocks = len(map_status[self.BS_INVALID])
    if num_invalid_blocks > 0:
      self.log.msg(Log.INFO, "%d invalid blocks found" % num_invalid_blocks)
    
    # store block map
    self.block_infos = block_infos
    self.map_status = map_status
    self.map_type = map_type
  
  def any_chance_of_fs(self):
    """is there any chance to find a FS on this block device?"""
    num_dirs = len(self.map_type[self.BT_DIR])
    num_files = len(self.map_type[self.BT_FILE_HDR])
    num_roots = len(self.map_type[self.BT_ROOT])
    return (num_files > 0) or ((num_roots + num_dirs) > 0)
    
  def get_blocks_of_type(self, t):
    return self.map_type[t]

  def get_blocks_with_key_value(self, key, value):
    res = []
    for bi in self.block_infos:
      if hasattr(bi, key):
        v = getattr(bi, key)
        if v == value:
          res.append(bi)
    return res

  def get_block(self, num):
    if num >= 0 and num < len(self.block_infos):
      return self.block_infos[num]
    else:
      return None

  def dump(self):
    for b in self.block_infos:
      print b

