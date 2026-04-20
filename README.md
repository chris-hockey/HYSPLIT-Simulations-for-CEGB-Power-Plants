# HYSPLIT-Simulations-for-CEGB-Power-Plants on Fedora 43 x86_64 
Code and documentation for running batch HYSPLIT concentration simulations to look at the effect of coal-fired power plants on health outcomes across England and Wales.

Look at ```instructions/setting_up.md``` to get started and ```instructions/gui_fix.md``` to make a key fix to get the GUI working

Scripts in ```code/build/``` to:
1. Run API calls to download ERA5 data
2. Convert ERA5 data into months
3. Merge time-invariant geopotential data with time-varying pressure data
4. Convert monthy ERA5 data into HYSPLIT-readable ARL data with ```era52arl```

Some additional testing scripts with handling the output of individual concentration runs in Python in a GIS-workable format are also present