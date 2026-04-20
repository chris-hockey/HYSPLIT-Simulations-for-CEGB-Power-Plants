# HYSPLIT GUI Setup on Fedora 43 — What We Did and Why

---

## The Problem

The HYSPLIT GUI is a Tcl/Tk script (`guicode/hysplit.tcl`). When launched,
it crashed immediately with:

```
can't read "tcl_dir": no such variable
```

The error was on line 611, inside a `namespace eval html` block:

```tcl
namespace eval html {
  source [file join $tcl_dir .. guicode htmlbrws.tcl ]
  namespace export load_html
}
```

In Tcl, `namespace eval` executes in its own namespace context. The variable
`tcl_dir` is set in the global namespace, but inside `namespace eval html`,
`$tcl_dir` looks for a namespace-local variable `html::tcl_dir` which does
not exist. The correct way to reference a global variable from inside a
namespace is `$::tcl_dir`.

This is a bug in HYSPLIT's Tcl script — it worked on older versions of
Tcl/Tk (as on Linux Mint) but fails on the newer Tcl/Tk shipped with
Fedora 43.

---

## The Fix

One line changed in `~/HYSPLIT/guicode/hysplit.tcl`:

```bash
sed -i \
  's|source \[file join \$tcl_dir \.\. guicode htmlbrws\.tcl \]|source [file join $::tcl_dir .. guicode htmlbrws.tcl ]|' \
  ~/HYSPLIT/guicode/hysplit.tcl
```

This replaces `$tcl_dir` with `$::tcl_dir` on line 611, making the global
variable accessible from within the namespace.

---

## Dead ends (do not repeat)

During diagnosis we also patched lines 157 and 160 of `hysplit.tcl` to
hardcode paths. These were reverted before applying the real fix:

```bash
sed -i \
  's|source /home/chris/HYSPLIT/guicode/normalfile.tcl|source [file join [file dirname [info script] ] .. guicode normalfile.tcl]|' \
  ~/HYSPLIT/guicode/hysplit.tcl

sed -i \
  's|set infoScriptDir /home/chris/HYSPLIT/guicode|set infoScriptDir [file dirname [info script] ]|' \
  ~/HYSPLIT/guicode/hysplit.tcl
```

Those lines should be in their original state. Only line 611 is changed.

---

## Launching the GUI

The GUI must be launched from `~/HYSPLIT/working` because it looks for
`default_exec` in the current directory. `default_exec` contains all the
directory paths the GUI needs.

```bash
cd ~/HYSPLIT/working
wish ~/HYSPLIT/guicode/hysplit.tcl &
```

---

## Desktop launcher

To launch from a desktop icon without opening a terminal:

```bash
cat > ~/.local/share/applications/hysplit.desktop << 'EOF'
[Desktop Entry]
Name=HYSPLIT
Comment=HYSPLIT Dispersion Model GUI
Exec=bash -c "cd /home/chris/HYSPLIT/working && wish /home/chris/HYSPLIT/guicode/hysplit.tcl"
Icon=/home/chris/HYSPLIT/working/icon63.png
Terminal=false
Type=Application
Categories=Science;
EOF
```

The launcher will appear in the applications menu under Science. It can
also be pinned to the taskbar.