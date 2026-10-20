# -*- coding: utf-8 -*-
import sys
import tkinter as tk
from scada_tracelog.gui.app_window import MainWindow

def main():
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()

if __name__ == "__main__":
    main()
