from tkinter import *
from config import settings

def palette():
   """Return the current colour palette (dark or light) based on config."""
   return settings.darkColours if settings.config["dark_mode_enabled"] else settings.lightColours

class ToolTip:
   """
      Lightweight tooltip that appears when the mouse hovers over a widget.

      Create and attach in one line:
         ToolTip(widget, "Explanation text shown on hover")
   """
   def __init__(self, widget, text):
      self.widget = widget
      self.text = text
      self.tipwindow = None
      widget.bind('<Enter>', self.enter)
      widget.bind('<Leave>', self.leave)

   def enter(self, event):
      if self.tipwindow or not self.text:
         return
      x = self.widget.winfo_rootx() + 20
      y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
      self.tipwindow = tw = Toplevel(self.widget)
      tw.wm_overrideredirect(True)
      tw.wm_geometry("+{}+{}".format(x, y))
      Label(tw, text=self.text, justify=LEFT,
            bg="#ffffe0", fg="#1e1e1e", relief=SOLID, borderwidth=1,
            padx=6, pady=4).pack()

   def leave(self, event):
      if self.tipwindow:
         self.tipwindow.destroy()
         self.tipwindow = None
