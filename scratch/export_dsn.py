import sys, os
import wx; app = wx.App(False)
import pcbnew

wx.Log.EnableLogging(False)
src = os.path.abspath(sys.argv[1])
b = pcbnew.LoadBoard(src)
assert b is not None, f"LoadBoard failed: {src}"
for t in list(b.GetTracks()):
    b.Remove(t)
pcbnew.SaveBoard(os.path.abspath("unrouted.kicad_pcb"), b)
print("DSN:", pcbnew.ExportSpecctraDSN(b, os.path.abspath("board.dsn")))