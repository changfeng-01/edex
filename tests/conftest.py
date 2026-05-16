from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def extract_fixture_zip(zip_name: str, tmp_path: Path) -> Path:
    raw = write_raw_fixture(tmp_path / "raw")
    archive = raw / zip_name
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(tmp_path)
    return tmp_path


def write_raw_fixture(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    _write_zip(raw_dir / "v1.zip", "v1/8T1C.netlist", V1_NETLIST)
    _write_zip(raw_dir / "v8.zip", "v8/8T1C_v8.netlist", V8_NETLIST, "v8/8T1C_v8_netlist.mapping", V8_MAPPING)
    (raw_dir / "评价指标表.html").write_text(METRIC_TABLE_HTML, encoding="utf-8")
    return raw_dir


def write_extracted_fixture(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    v8 = root / "v8"
    v8.mkdir(parents=True, exist_ok=True)
    (v8 / "8T1C_v8.netlist").write_text(V8_NETLIST, encoding="utf-8")
    (v8 / "8T1C_v8_netlist.mapping").write_text(V8_MAPPING, encoding="utf-8")
    v1 = root / "v1"
    v1.mkdir(parents=True, exist_ok=True)
    (v1 / "8T1C.netlist").write_text(V1_NETLIST, encoding="utf-8")
    return root


def _write_zip(path: Path, first_name: str, first_text: str, second_name: str | None = None, second_text: str | None = None) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(first_name, first_text)
        if second_name and second_text is not None:
            zf.writestr(second_name, second_text)


V1_NETLIST = """\
m7 clk pu output ntft L=5u W=850u
m6 output pd vss ntft L=5u W=360u
m5 output reset vss ntft L=5u W=360u
m4 pd pu vss ntft L=5u W=280u
m3 clkb clkb pd ntft L=8u W=40u
m2 pu pd vss ntft L=5u W=180u
m1 pu reset vss ntft L=5u W=180u
m0 input input pu ntft L=5u W=200u
CC0 pu output 800f
"""


V8_NETLIST = """\
.SUBCKT sub_1_8T1C clk clkb input output reset vss
m7 clk pu output ntft L=5u W=850u
m6 output pd vss ntft L=5u W=360u
m5 output reset vss ntft L=5u W=360u
m4 pd pu vss ntft L=5u W=280u
m3 clkb clkb pd ntft L=8u W=40u
m2 pu pd vss ntft L=5u W=180u
m1 pu reset vss ntft L=5u W=180u
m0 input input pu ntft L=5u W=200u
CC0 pu output 800f
.ENDS sub_1_8T1C
Xdummy clk clkb o8 net50 vss vss sub_1_8T1C
Xs1 clk clkb stv o1 o2 vss sub_1_8T1C
Xs2 clkb clk o1 o2 o3 vss sub_1_8T1C
Xs3 clk clkb o2 o3 o4 vss sub_1_8T1C
Xs4 clkb clk o3 o4 o5 vss sub_1_8T1C
Xs5 clkb clk o7 o8 net50 vss sub_1_8T1C
Xs6 clk clkb o6 o7 o8 vss sub_1_8T1C
Xs7 clkb clk o5 o6 o7 vss sub_1_8T1C
Xs8 clk clkb o4 o5 o6 vss sub_1_8T1C
Vvss vss 0 DC -5
Vclk clk 0 PULSE(-5 15 5.25u 100n 100n 10u 20u)
Vclkb clkb 0 PULSE(15 -5 4.75u 100n 100n 10u 20u)
Vstv stv 0 PULSE(-5 15 0 100n 100n 10u 100u)
"""


V8_MAPPING = """\
8T1C 8T1C C sub_1_8T1C
8T1C 8T1C P clkb 2
8T1C 8T1C P vss 6
8T1C 8T1C P clk 1
8T1C 8T1C P reset 5
8T1C 8T1C P input 3
8T1C 8T1C P output 4
8T1C 8T1C I C0 CC0
8T1C 8T1C I M0 m0
8T1C 8T1C I M1 m1
8T1C 8T1C I M2 m2
8T1C 8T1C I M3 m3
8T1C 8T1C I M4 m4
8T1C 8T1C I M5 m5
8T1C 8T1C I M6 m6
8T1C 8T1C I M7 m7
8T1C 8T1C N clkb clkb
8T1C 8T1C N vss vss
8T1C 8T1C N clk clk
8T1C 8T1C N pd pd
8T1C 8T1C N reset reset
8T1C 8T1C N input input
8T1C 8T1C N output output
8T1C 8T1C N pu pu
8T1C 8T1C_v8 C sub_0_8T1C_v8
8T1C 8T1C_v8 I clkb Vclkb
8T1C 8T1C_v8 I dummy Xdummy
8T1C 8T1C_v8 I vss Vvss
8T1C 8T1C_v8 I stv Vstv
8T1C 8T1C_v8 I clk Vclk
8T1C 8T1C_v8 I s1 Xs1
8T1C 8T1C_v8 I s2 Xs2
8T1C 8T1C_v8 I s3 Xs3
8T1C 8T1C_v8 I s4 Xs4
8T1C 8T1C_v8 I s5 Xs5
8T1C 8T1C_v8 I s6 Xs6
8T1C 8T1C_v8 I s7 Xs7
8T1C 8T1C_v8 I s8 Xs8
8T1C 8T1C_v8 N o1 o1
8T1C 8T1C_v8 N o2 o2
8T1C 8T1C_v8 N o3 o3
8T1C 8T1C_v8 N o4 o4
8T1C 8T1C_v8 N o5 o5
8T1C 8T1C_v8 N o6 o6
8T1C 8T1C_v8 N o7 o7
8T1C 8T1C_v8 N o8 o8
8T1C 8T1C_v8 N clkb clkb
8T1C 8T1C_v8 N vss vss
8T1C 8T1C_v8 N stv stv
8T1C 8T1C_v8 N clk clk
8T1C 8T1C_v8 N net50 net50
8T1C 8T1C_v8 N GND! 0
fpd ntft P D D
fpd ntft P G G
fpd ntft P S S
"""


METRIC_TABLE_HTML = """\
<table>
<tr><th>层级</th><th>指标</th><th>符号</th><th>观察对象</th><th>物理意义</th><th>提取方法</th><th>初始判据</th><th>类型</th><th>关联参数</th></tr>
<tr><td>功能</td><td>扫描顺序</td><td>Seq</td><td>o i</td><td>逐级扫描</td><td>边沿排序</td><td>通过</td><td>hard</td><td>时钟</td></tr>
<tr><td>功能</td><td>有效脉冲存在性</td><td>PulseExist_i</td><td>o i</td><td>输出被选通</td><td>窗口检测</td><td>存在</td><td>hard</td><td>驱动</td></tr>
<tr><td>功能</td><td>误触发</td><td>FalseTrigger_i</td><td>o i</td><td>非选通异常</td><td>阈值检测</td><td>无</td><td>hard</td><td>噪声</td></tr>
<tr><td>功能</td><td>相邻级重叠</td><td>Overlap_i</td><td>o i</td><td>相邻选通重叠</td><td>区间交集</td><td>小</td><td>hard</td><td>时序</td></tr>
<tr><td>质量</td><td>输出高电平</td><td>VOH_i</td><td>o i</td><td>高电平裕量</td><td>窗口均值</td><td>高</td><td>diagnosis</td><td>驱动</td></tr>
<tr><td>质量</td><td>输出低电平</td><td>VOL_i</td><td>o i</td><td>低电平风险</td><td>非选通最大值</td><td>低</td><td>diagnosis</td><td>下拉</td></tr>
<tr><td>质量</td><td>脉冲宽度</td><td>Width_i</td><td>o i</td><td>选通宽度</td><td>窗口宽度</td><td>接近目标</td><td>diagnosis</td><td>时钟</td></tr>
<tr><td>质量</td><td>传播延迟</td><td>Delay_i</td><td>o i</td><td>级间延迟</td><td>边沿差</td><td>稳定</td><td>diagnosis</td><td>负载</td></tr>
<tr><td>质量</td><td>上升时间</td><td>Rise_i</td><td>o i</td><td>上升速度</td><td>10-90%</td><td>短</td><td>diagnosis</td><td>驱动</td></tr>
<tr><td>质量</td><td>下降时间</td><td>Fall_i</td><td>o i</td><td>下降速度</td><td>90-10%</td><td>短</td><td>diagnosis</td><td>下拉</td></tr>
<tr><td>稳定性</td><td>非选通纹波</td><td>Ripple_i</td><td>o i</td><td>保持稳定</td><td>峰峰值</td><td>小</td><td>diagnosis</td><td>寄生</td></tr>
<tr><td>稳定性</td><td>最弱级高电平</td><td>VOH_min</td><td>all</td><td>最弱级</td><td>最小值</td><td>高</td><td>summary</td><td>驱动</td></tr>
<tr><td>稳定性</td><td>最大非选通风险</td><td>Risk_max</td><td>all</td><td>最大风险</td><td>最大值</td><td>低</td><td>summary</td><td>稳定性</td></tr>
<tr><td>一致性</td><td>延迟离散度</td><td>Delay_std</td><td>all</td><td>一致性</td><td>标准差</td><td>小</td><td>summary</td><td>时钟</td></tr>
<tr><td>一致性</td><td>高电平离散度</td><td>VOH_std</td><td>all</td><td>一致性</td><td>标准差</td><td>小</td><td>summary</td><td>驱动</td></tr>
<tr><td>成本</td><td>代理成本</td><td>Cost</td><td>all</td><td>面积成本</td><td>W/C proxy</td><td>低</td><td>proxy</td><td>尺寸</td></tr>
</table>
"""
