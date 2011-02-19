"""
 chumbylib.py  | v1.0 beta  |  2/11  |  Alex Hiam
 
 
 This code released under the GNU General Public License v3
 
 Feel free to send any feedback or suggestions:
  wampumphysics@gmail.com
 
 Python library for the Chumby Hacker Board v1 to gain easy access to the 
 programmable registers, as well as support for a Nokia 5110 graphic lcd. 
 
 Currently only supports pins on the 2x13 header, but they're easy to add. 
 Refer to chapter 37 of processor datasheet:
  http://cache.freescale.com/files/dsp/doc/ref_manual/IMX23RM.pdf

 Much thanks to madox who wrote some similar python code for the Infocast that
 I referenced for this project. I had been using regutil to set pins before I 
 found it; madox worked out the kinks of writing straight to the mem file from
 python. Check out his code here:
  http://code.google.com/p/madox/source/browse/trunk/chumby/chumby.py?r=5
  http://www.madox.net/
  
 Lcd can be purchased with breakout board from SparkFun Electronics:
  http://www.sparkfun.com/products/10168 
 They also have th datasheet up:
  http://www.sparkfun.com/datasheets/LCD/Monochrome/Nokia5110.pdf
 
 Referenced these couple example Arduino sketches that use the same display:
  http://www.arduino.cc/playground/Code/PCD8544
 
 Pins D00 - D04 start configured as GPIO pins, but when startLcd() is called
 without specifying other pins, they are used for the glcd. 
 They may be reclaimed one at a time using setOut() or setIn, or all at once 
 with stopLcd(), which first clears the display.
 
 LCD Lcd pins default to:
 
  i.MX23 Pin  |   LCD pin
  ------------|---------
      D00     |    SCLK
      D01     |    DN
      D02     |    D/C
      D03     |    RST
      D04     |    SCE
      
"""

from mmap import mmap
import struct, time


class CHB:
  def __init__(self, mux_to_activate=[1]*7):
    # Offsets:
    self.mmap_offset = 0x7FFFF000  # Maximum ofset mmap will take
    self.PINCTRL_offset = 0x80018000 - self.mmap_offset;
    file = open("/dev/mem", "r+b")
    mmap_size = (0x2c + 4) + 0x80018000 - self.mmap_offset
    self.mem = mmap(file.fileno(), 0x20000, offset=self.mmap_offset)
    self._pins()
    self._setCmds()
    self._activatePins()
    # To keep track of what's what:
    self.din = []
    self.dout = []
    self.lcdpins = []
    
  
  def write(self, pin, state):
    """ Sets given pin to state if pin not in input list.  """
    try: 
      pinVals = self.pins[pin]
    except:
      return 
    if (pin in self.din) or (pin in self.lcdpins) : return
    if state:
      self._setMem(self.dout_set % pinVals[1], pinVals[2])
      return
    self._setMem(self.dout_clr % pinVals[1], pinVals[2])
    
    
  def read(self, pin):
    """ Returns given pin to state if pin not in output list.  """
    try: 
      pinVals = self.pins[pin]
    except:
      return 
    if (pin in self.dout) or (pin in self.lcdpins): return None
    reg = self._getMem(self.din_state % pinVals[1])
    state = reg & pinVals[2]
    if state: return 1
    return 0

  def setOut(self, pin, pull=0):
    """
     Sets given pin to an output and updates status lists.
     Pullup resister in enabled or disabled by pull (0 or 1).
    """
    try: 
      pinVals = self.pins[pin]
    except:
      return
    self._setMem(self.doe_set % pinVals[1], pinVals[2])
    if pull:
      self._setMem(self.pull_set % pinVals[1], pinVals[2])
    else:
      self._setMem(self.pull_clr % pinVals[1], pinVals[2])
    if not (pin in self.dout): self.dout.append(pin)
    if pin in self.din: self.din.remove(pin)
    if pin in self.lcdpins: self.lcdpins.remove(pin)
    
    
  def setIn(self, pin, pull=0):
    """
     Sets given pin to an input and updates status lists.
     Pullup resister in enabled or disabled by pull (0 or 1).
    """
    try: 
      pinVals = self.pins[pin]
    except:
      return
    self.din.append(pin)
    self._setMem(self.doe_clr % pinVals[1], pinVals[2])
    self._setMem(self.din_set % pinVals[1], pinVals[2])
    if pull:
      self._setMem(self.pull_set % pinVals[1], pinVals[2])
    else:
      self._setMem(self.pull_clr % pinVals[1], pinVals[2])
    if not (pin in self.din): self.din.append(pin)
    if pin in self.dout: self.dout.remove(pin)
    if pin in self.lcdpins: self.lcdpins.remove(pin)
    
    
  def status(self):
    s = "  inputs: %s \n outputs: %s" % (self.din, self.dout)
    if self.lcdpins: s += " \n     lcd: %s" % self.lcdpins
    return s
    
  
  def startLcd(self, pins=['D0','D1','D2','D3','D4']):
    """ Creates lcd instance with given pins. """
    self.lcd = LCD(self, pins)
  
  
  def _setMem(self, loc, value):
    """
     Sets mem[address] to value.
     -note: I started had these lines at the start of this function:
       reg = self._getMem(loc)  
       reg |= value
     and it calls to write were effecting multiple pin. It turns out
     that the i.MX23RM is set up to maintain the states of its registers.
     You only high bits will cause change. 
    """ 
    loc = self.reg_cmd[loc]
    self.mem[loc:loc+4] = self._pack_32bit(value)
  
  

  def _getMem(self, loc):
    """ Returns int of 32-bits from loc in mem file. """
    loc = self.reg_cmd[loc]
    packed = self.mem[loc:loc+4]
    return struct.unpack("<L", packed)[0]
    
  
  def _activatePins(self):
    """ Sets all pins in self.pins to GPIO. """
    for i in self.pins:
      self._setMem(self.muxsel % self.pins[i][0][0], self.pins[i][0][1])
        
  
  def _pack_32bit(self, value):
    """
     Straight from madox's code.
     Returns value in correct format for writing to mem file.
    """
    return struct.pack("<L", value) 
  
  
  def __str__(self):
    return self.status()
    
    
  def _pins(self):
    """ Creates dictionary of pins. """
    # pin muxsel, bank, and address by name on CHB silkscreen -
    # pins["D0"][0] = [muxsel, mux bits],pins["D0"][1] = bank number, 
    # pins["D0"][2] = address.
    # note - Despite their names, I'm configuring all these pins as
    # GPIOs for now, although I plan to update this to allow at least
    # analog input functionality. 
    self.pins = { "D0" : [[0, 0x0003],     0, 0x00000001],
                  "D1" : [[0, 0x000c],     0, 0x00000002],
                  "D2" : [[0, 0x0030],     0, 0x00000004],
                  "D3" : [[0, 0x00c0],     0, 0x00000008],
                  "D4" : [[0, 0x0300],     0, 0x00000010],
                  "D5" : [[0, 0x0c00],     0, 0x00000020],
                  "D6" : [[0, 0x3000],     0, 0x00000040],
                  "D7" : [[0, 0xc000],     0, 0x00000080], 
                 "SCL" : [[1, 0x30000000], 0, 0x40000000],
                 "SDA" : [[1, 0xc0000000], 0, 0x80000000],
                 # "A2" : [[4, 0x00c00000], 2, 0x00000800],
                 # "A3" : [[4, 0x03000000], 2, 0x00001000],
                 # "A4" : [[4, 0x0c000000], 2, 0x00002000],
                 # "A5" : [[4, 0x30000000], 2, 0x00004000],
                 #"PM1" : [[3, 0x00c00000], 1, 0x08000000]
                 #"PM2" : [[3, 0x03000000], 1, 0x10000000],
                 #"PM3" : [[3, 0x0c000000], 1, 0x20000000],
                 #"PM4" : [[3, 0x30000000], 1, 0x40000000]
                }
                #**********************************************
                # For some reason when I include any of the pins
                # that I have commented out, the chumby reboots   
                # when _activatePins() is executed!
                #**********************************************
             # -note: problem identified (I made a dumb mistake!)
             #  will fix and update soon
                
                
  def _setCmds(self):
    """ Creates simple to call commands for setting pin states.  """
    
    self.muxsel = "HW_PINCTRL_MUXSEL%i_SET"
    self.doe_set = "HW_PINCTRL_DOE%i_SET"
    self.doe_clr = "HW_PINCTRL_DOE%i_CLR"
    self.dout_set = "HW_PINCTRL_DOUT%i_SET"
    self.dout_clr = "HW_PINCTRL_DOUT%i_CLR"
    self.dout_tog = "HW_PINCTRL_DOUT%i_TOG"
    self.din_state = "HW_PINCTRL_DIN%i"
    self.din_set = "HW_PINCTRL_DIN%i_SET"
    self.din_clr = "HW_PINCTRL_DIN%i_CLR"
    self.pull_set = "HW_PINCTRL_PULL%i_SET"
    self.pull_clr = "HW_PINCTRL_PULL%i_CLR"
    
    
    self.reg_cmd = { "HW_PINCTRL_MUXSEL0_SET" : 0x104 + self.PINCTRL_offset,
                     "HW_PINCTRL_MUXSEL1_SET" : 0x114 + self.PINCTRL_offset,
                     "HW_PINCTRL_MUXSEL2_SET" : 0x124 + self.PINCTRL_offset,
                     "HW_PINCTRL_MUXSEL3_SET" : 0x134 + self.PINCTRL_offset,
                     "HW_PINCTRL_MUXSEL4_SET" : 0x144 + self.PINCTRL_offset,
                     "HW_PINCTRL_MUXSEL5_SET" : 0x154 + self.PINCTRL_offset,
                     "HW_PINCTRL_MUXSEL6_SET" : 0x164 + self.PINCTRL_offset,
                     "HW_PINCTRL_MUXSEL7_SET" : 0x174 + self.PINCTRL_offset,
            
                        "HW_PINCTRL_DOE0_SET" : 0x704 + self.PINCTRL_offset,
                        "HW_PINCTRL_DOE0_CLR" : 0x708 + self.PINCTRL_offset,
                        "HW_PINCTRL_DOE1_SET" : 0x714 + self.PINCTRL_offset,
                        "HW_PINCTRL_DOE1_CLR" : 0x718 + self.PINCTRL_offset,
                        "HW_PINCTRL_DOE2_SET" : 0x724 + self.PINCTRL_offset,
                        "HW_PINCTRL_DOE2_CLR" : 0x728 + self.PINCTRL_offset,
               
                       "HW_PINCTRL_DOUT0_SET" : 0x504 + self.PINCTRL_offset,
                       "HW_PINCTRL_DOUT0_CLR" : 0x508 + self.PINCTRL_offset,
                       "HW_PINCTRL_DOUT0_TOG" : 0x50c + self.PINCTRL_offset,
                       "HW_PINCTRL_DOUT1_SET" : 0x514 + self.PINCTRL_offset,
                       "HW_PINCTRL_DOUT1_CLR" : 0x518 + self.PINCTRL_offset,
                       "HW_PINCTRL_DOUT1_TOG" : 0x51c + self.PINCTRL_offset,
                       "HW_PINCTRL_DOUT2_SET" : 0x524 + self.PINCTRL_offset,
                       "HW_PINCTRL_DOUT2_CLR" : 0x528 + self.PINCTRL_offset,
                       "HW_PINCTRL_DOUT2_TOG" : 0x52c + self.PINCTRL_offset,
                      
                            "HW_PINCTRL_DIN0" : 0x600 + self.PINCTRL_offset,
                        "HW_PINCTRL_DIN0_SET" : 0x604 + self.PINCTRL_offset,
                        "HW_PINCTRL_DIN0_CLR" : 0x608 + self.PINCTRL_offset,
                            "HW_PINCTRL_DIN1" : 0x610 + self.PINCTRL_offset,
                        "HW_PINCTRL_DIN1_SET" : 0x614 + self.PINCTRL_offset,
                        "HW_PINCTRL_DIN1_CLR" : 0x618 + self.PINCTRL_offset,
                            "HW_PINCTRL_DIN2" : 0x620 + self.PINCTRL_offset,
                        "HW_PINCTRL_DIN2_SET" : 0x624 + self.PINCTRL_offset,
                        "HW_PINCTRL_DIN2_CLR" : 0x628 + self.PINCTRL_offset,
                        
                       "HW_PINCTRL_PULL0_SET" : 0x404 + self.PINCTRL_offset,
                       "HW_PINCTRL_PULL0_CLR" : 0x408 + self.PINCTRL_offset,
                       "HW_PINCTRL_PULL1_SET" : 0x414 + self.PINCTRL_offset,
                       "HW_PINCTRL_PULL1_CLR" : 0x418 + self.PINCTRL_offset,
                       "HW_PINCTRL_PULL2_SET" : 0x424 + self.PINCTRL_offset,
                       "HW_PINCTRL_PULL2_CLR" : 0x428 + self.PINCTRL_offset }
                      
         
         

class LCD:
  """ Nokia 5110 class. Must be created by CHB instance. """ 
  def __init__(self, chb, pins):
    self.chb = chb
    self.pins = pins
    self._lcdInit()
    
   
  def write(self, data, dc=1):
    """
     Writes 8 bits to the lcd shift register.
     dc=0 for command mode, dc=1 for data mode.
    """
    #----- Way too slow -------------------
    self.chb.write(self.lcd["dc"], dc)
    self.chb.write(self.lcd["sce"], 0)
    for i in range(8):
      self.chb.write(self.lcd["sclk"], 0)
      if (128>>i & data): self.chb.write(self.lcd["dn"], 1)
      else: self.chb.write(self.lcd["dn"], 0)
      self.chb.write(self.lcd["sclk"], 1)
    self.chb.write(self.lcd["sce"], 1)

  def clear(self):
    for i in range(84*6):
      self.write(0x00)

  def xy(self, x, y):
    """ 
     Sets cursor to location (x, y).
     x should be in range 0-84 (pixel index)
     y should be in range 0-5 (line number)
    """
    self.write(0x80 | x, 0)
    self.write(0x40 | y, 0)  
  
  
  def _lcdInit(self):   
    """ Initializes lcd. """
    # Easier to the address lcd pins by their names:
    self.lcd = { "sclk" : self.pins[0],
                   "dn" : self.pins[1],
                   "dc" : self.pins[2],
                  "rst" : self.pins[3],
                  "sce" : self.pins[4] }  
    self.chb.lcdpins = []
    for i in self.lcd:
      self.chb.setOut(self.lcd[i])
      self.chb.lcdpins.append(i)
    
    self.chb.write(self.lcd["rst"],0)
    self.chb.write(self.lcd["rst"],1)
    self.write(0x21, 0)
    self.write(0xbf, 0)
    self.write(0x04, 0)
    self.write(0x14, 0)
    self.write(0x0c, 0)
    self.write(0x20, 0)
    self.write(0x0c, 0)
    self.clear()
    