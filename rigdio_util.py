import colorsys

# thanks to stackoverflow: http://stackoverflow.com/questions/27650712/python-time-in-format-dayshoursminutesseconds-to-seconds
def timeToSeconds(time):
   multi = [1,60,3600,86400]
   try:
      time = [float(x) for x in time.split(":")]
      t_ret = 0
      for i,t in enumerate(reversed(time)):
         t_ret += multi[i] * t
      return t_ret
   except ValueError:
      return None

def volumeColor(value, vmax=200):
   value = int(value)
   # Map slider value to a hue from 270° (purple) at 0 to 0° (red) at vmax
   hue = 270.0 * (1 - max(0, min(value, vmax)) / vmax) / 360.0
   r, g, b = colorsys.hsv_to_rgb(hue, 0.4, 0.8)
   return '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255))

# numeric version of sliderToDb: returns -inf for mute instead of a string
def _sliderToDb(value):
   value = int(value)
   if value <= 0:
      return float('-inf')
   if value < 100:
      return -20 * (1 - value / 100)
   return 20 * (value - 100) / 100

# inverse of _sliderToDb: converts a dB value back to a slider value.
# values outside [-20, +20] map outside [0, 200], which is intentional so the
# combined volume can exceed a single slider's range (mpv handles it via the
# cubic volume scale in legacy._toMpvVolume).
def _dbToSlider(dB):
   if dB == float('-inf'):
      return 0
   if dB < 0:
      return 100 * (1 + dB / 20)
   return 100 + 5 * dB

def sliderToDb(value):
   dB = _sliderToDb(int(value))
   if dB == float('-inf'):
      return "Mute"
   return "{:+.0f}".format(dB)

# combine two slider values (each 0-200, 100=unity) by summing their dB.
# used to apply a chants-only volume offset on top of the master volume.
# if either slider is muted (0), the result is muted.
def combineVolume(master, chants):
   master = int(master)
   chants = int(chants)
   if master <= 0 or chants <= 0:
      return 0
   return _dbToSlider(_sliderToDb(master) + _sliderToDb(chants))

def main():
   print(timeToSeconds("1:30"))
   print(timeToSeconds("0:40"))

if __name__ == '__main__':
   main()