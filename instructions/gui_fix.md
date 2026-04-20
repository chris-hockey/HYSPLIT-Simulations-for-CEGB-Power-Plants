# HYSPLIT GUI Launch Fix on Fedora 43
## The problem

When launching the HYSPLIT GUI on Fedora 43 with:

```bash
wish ~/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/guicode/hysplit.tcl &
```

It crashed with:

```
Error in startup script: can't read "tcl_dir": no such variable
    while executing
"file join $tcl_dir .. guicode htmlbrws.tcl "
    (in namespace eval "::html" script line 2)
```

## What was happening

The GUI is a Tcl/Tk script. Early in the script, it sets a variable
called `tcl_dir` holding the path to the guicode directory. Later,
on line 611, it tries to use that variable from inside a `namespace
eval html { ... }` block:

```tcl
namespace eval html {
  source [file join $tcl_dir .. guicode htmlbrws.tcl ]
  namespace export load_html
}
```

In Tcl, a `namespace eval` block creates its own variable scope.
Inside that block, bare `$tcl_dir` refers to a variable inside the
`html` namespace — which doesn't exist — rather than the global
`tcl_dir` that was set outside.

This bug has always been in the HYSPLIT GUI but went unnoticed on
older versions of Tcl/Tk. The stricter variable scoping in the
Tcl version shipped with Fedora 43 exposes it.

## The fix

Change `$tcl_dir` to `$::tcl_dir` on line 611. The `::` prefix in Tcl
means "look for this variable in the global namespace", which is
where it was actually defined.

```bash
sed -i \
  's|source \[file join \$tcl_dir \.\. guicode htmlbrws\.tcl \]|source [file join $::tcl_dir .. guicode htmlbrws.tcl ]|' \
  ~/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/guicode/hysplit.tcl
```

## How to launch the GUI

```bash
cd ~/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/working
wish ~/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/guicode/hysplit.tcl &
```

The `cd` into `working/` matters — the GUI looks for `default_exec`
in the current directory to locate the other HYSPLIT paths.

## Desktop launcher

To avoid opening a terminal every time, create a desktop entry:

```bash
cat > ~/.local/share/applications/hysplit.desktop << 'EOF'
[Desktop Entry]
Name=HYSPLIT
Comment=HYSPLIT Dispersion Model GUI
Exec=bash -c "cd /home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/working && wish /home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/guicode/hysplit.tcl"
Icon=/home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/guicode/hylogos.gif
Terminal=false
Type=Application
Categories=Science;
EOF

update-desktop-database ~/.local/share/applications/
```

After this, HYSPLIT appears in the applications menu under Science
and can be pinned to the taskbar.