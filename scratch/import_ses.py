import os
import wx; app = wx.App(False); wx.Log.EnableLogging(False)
import pcbnew

b = pcbnew.LoadBoard(os.path.abspath("unrouted.kicad_pcb"))
assert b is not None, "LoadBoard failed: unrouted.kicad_pcb"
assert os.path.exists("board.ses"), "board.ses missing"
print("SES:", pcbnew.ImportSpecctraSES(b, os.path.abspath("board.ses")))

filler = pcbnew.ZONE_FILLER(b)
filler.Fill(b.Zones())

pcbnew.SaveBoard(os.path.abspath("routed.kicad_pcb"), b)