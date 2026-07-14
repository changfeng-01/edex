* Description: simulation for cankao12/00main_panel/schematic
.option search="/home/siduser04"
.inc "/home/siduser04/cankao12_00main_panel_schematic_ALPS/cankao12_00main_panel_schematic.netlist"
.param
+Rg_dot=1
+Cg_dot=50f
+Rd_dot=2
+Cd_dot=25f
+Cgs=1f
+CstClc=187f
+Wpixel=10u
+Lpixel=4u
+r_data_i=150
+Rgate=ResH*3*Rg_dot
+Cgate=ResH*3*Cg_dot
+Rdata=ResV*Rd_dot
+Cdata=ResV*Cd_dot
+Cst=CstClc*0.9
+Clc=CstClc*0.1
.param
+r_ttr_i=20
+r_vdd_i=20
+r_vgl_i=20
+r_clk_i=20
+r_stv_i=20
+r_stv=600
+r_clk=500
+r_ttr=700
+r_vdd=600
+r_vgl=600
+cclk_ttr_unit=11f
+cclk_vdd_unit=11f
+cclk_vgl_unit=11f
+cclk_unit=1f
+r_goa=4
+V_GOA=0.5*(ResV+Dum_GOA)
+Dum_GOA=8
+r_ttr_unit=r_ttr/V_GOA
+r_vdd_unit=r_vdd/V_GOA
+r_vgl_unit=r_vgl/V_GOA
+r_clk_unit=r_clk/V_GOA
.param
+C1=4p
+Wt1=500u
+Lt1=3.5u
+Wt2=250u
+Lt2=3.5u
+Wt3=4000u
+Lt3=3.5u
+Wt4=50u
+Lt4=3.5u
+Wt5=50u
+Lt5=3.5u
+Wt6=250u
+Lt6=3.5u
+Wt7=250u
+Lt7=3.5u
+Wt8=50u
+Lt8=3.5u
+Wt9=50u
+Lt9=3.5u
+Wt10=400u
+Lt10=3.5u
+Wt11=400u
+Lt11=3.5u
.param
+ResH=1680
+ResV=720
.param
+VDH=10.2V
+VDL=0.2V
+VGH=22V
+VGL=-8V
+Vcom=5.2V
+tr=0.2u
+tf=0.2u
+dtr=0.3u
+dtf=0.3u
+H1=Frame/Vtotal
+Frame=1/Freq
+Freq=240
+V_Blank=30
+Vtotal=ResV+V_Blank
+GOE=5u
+clk_duty=0.5
+do_delay=1u+4*H1*(clk_duty-0.5)
+clk_delay=stv_delay+4*H1*(1-clk_duty)
+stv_delay=ttr_delay+1*H1
+ttr_delay=1u
+vdd_delay=1u
.inc "./modelfile/aa.mod.sp"
.inc "./modelfile/goa.mod.sp"
.temp 27
.option errpreset=moderate
.option reltol=0.001
.option abstol=1e-09
.option absv=5e-06
.option gmin=1e-12
.option itl1=200
.option itl4=8
.option tnom=27
.option scale=1
.option scalm=1
.option post
.option probe
.option postlvl=0
.option posttop=0
.option ingold=0
.tran 0.1u 4.2m 0 
.probe TRAN v(do)
.probe TRAN v(de)
.probe TRAN v(clk<1>)
.probe TRAN v(clk<2>)
.probe TRAN v(clk<3>)
.probe TRAN v(clk<4>)
.probe TRAN v(clk<5>)
.probe TRAN v(clk<6>)
.probe TRAN v(clk<7>)
.probe TRAN v(clk<8>)
.probe TRAN v(com)
.probe TRAN v(do_far)
.probe TRAN v(do_mid)
.probe TRAN v(doi)
.probe TRAN v(xi8<1>.pixel)
.probe TRAN v(xi8<2>.pixel)
.probe TRAN v(xi8<3>.pixel)
.probe TRAN v(xi8<4>.pixel)
.probe TRAN v(xi8<5>.pixel)
.probe TRAN v(xi8<6>.pixel)
.probe TRAN v(xi8<7>.pixel)
.probe TRAN v(xi8<8>.pixel)
.probe TRAN v(xi8<9>.pixel)
.probe TRAN v(xi0<91>.xi0<4>.pu)
.probe TRAN v(xi0<91>.xi0<4>.pd)
.probe TRAN v(xi0<91>.xi0<4>.output)
.probe TRAN v(xi0<91>.xi0<4>.input)
.probe TRAN v(xi0<91>.xi0<4>.clk)
.probe TRAN v(xi0<91>.xi0<4>.rst)
.probe TRAN v(xi0<91>.xi0<4>.vdd)
.probe TRAN v(xi0<2>.xi0<1>.input)
.probe TRAN v(xi0<2>.xi0<1>.pu)
.probe TRAN v(xi0<2>.xi0<1>.vdd)
.probe TRAN v(xi0<2>.xi0<1>.clk)
.probe TRAN v(xi0<2>.xi0<1>.output)
.probe TRAN v(xi0<2>.xi0<1>.rst)
.probe TRAN v(xi0<2>.xi0<1>.pd)
.probe TRAN v(g<2>)
.probe TRAN v(g<360>)
.probe TRAN v(g<720>)
.probe TRAN v(gate_mid<2>)
.probe TRAN v(gate_mid<360>)
.probe TRAN v(gate_mid<720>)
.probe TRAN v(gate_far<2>)
.probe TRAN v(gate_far<360>)
.probe TRAN v(gate_far<720>)
.end
