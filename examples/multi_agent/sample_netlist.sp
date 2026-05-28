* Minimal inverter-like netlist for multi-agent MVP tests
.SUBCKT inv in out vdd vss
XM1 out in vdd vdd sky130_fd_pr__pfet_01v8 W=1u L=0.15u
XM2 out in vss vss sky130_fd_pr__nfet_01v8 W=0.5u L=0.15u
.ENDS inv
XINV a y vdd vss inv
VDD vdd 0 DC 1.8
VIN a 0 PULSE(0 1.8 0 10p 10p 1n 2n)
CLOAD y 0 1f
