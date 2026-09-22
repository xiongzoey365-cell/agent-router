#!/usr/bin/env python3
"""Render the four labelled six-dimension distribution panels as an inline HTML fragment."""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / 'difficulty_signal_analysis' / 'six_dimension_visualization_data.json'
OUT = Path('/home/xiongziyan/.codex/visualizations/2026/09/22/01a0c7aa-48ed-72d0-bd98-fda7121549e9/six-dimension-distributions-detailed.html')
payload = json.loads(DATA.read_text(encoding='utf-8'))
compact = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
fragment = r'''
<div id="six-dimension-detailed">
  <h2>六维输出的四组分布</h2>
  <p class="text-small text-muted">仅使用 six_dimension 分支。标签：C=Code，M=Math，Q=QA，L=Logic，I=Instruction；数字为题目级别。红色为该面板异常度位于 25 题前 10% 的高离散关注点，不等同于统计显著离群或答错。</p>
  <section><h3>综合偏离同题型中心的程度</h3><div id="sd-composite"></div></section>
  <section><h3>文字输出特征分布</h3><div id="sd-text"></div></section>
  <section><h3>隐藏状态变化分布</h3><div id="sd-hidden"></div></section>
  <section><h3>隐藏复现分布</h3><div id="sd-recurrence"></div></section>
</div>
<style>
#six-dimension-detailed{width:100%;color:var(--foreground)}
#six-dimension-detailed section{margin-top:24px}
#six-dimension-detailed svg{width:100%;display:block}
#six-dimension-detailed .axis path,#six-dimension-detailed .axis line{stroke:var(--border)}
#six-dimension-detailed .axis text,#six-dimension-detailed .axis-title,#six-dimension-detailed .task-label,#six-dimension-detailed .metric-label{fill:var(--foreground);font-size:12px}
#six-dimension-detailed .task-label{font-weight:500;paint-order:stroke;stroke:var(--background);stroke-width:3px;stroke-linejoin:round}
#six-dimension-detailed .grid line{stroke:var(--border);stroke-opacity:.38}#six-dimension-detailed .grid path{display:none}
#six-dimension-detailed rect[data-chart-frame]{fill:transparent;stroke:var(--border)}
#six-dimension-detailed .zero{stroke:var(--muted-foreground);stroke-opacity:.7}
#six-dimension-detailed .leader{stroke:var(--muted-foreground);stroke-opacity:.45}
</style>
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
<script>
(()=>{
const root=document.getElementById('six-dimension-detailed');
const payload=__DATA__;
const rows=payload.rows;
const shortId=d=>({code_generation:'C',math_reasoning:'M',knowledge_qa:'Q',logical_reasoning:'L',instruction_following:'I'}[d.task_type]+d.difficulty_level);
const red=(d,key)=>d.outlier[key];
const color=(d,key)=>red(d,key)?'var(--red)':'var(--viz-series-1)';
function base(hostSel,height,aria){const host=root.querySelector(hostSel),w=Math.max(320,host.getBoundingClientRect().width||900);host.replaceChildren();const svg=d3.select(host).append('svg').attr('viewBox',`0 0 ${w} ${height}`).attr('role','img').attr('aria-label',aria);svg.append('title').text(aria);return {svg,w,height};}
function axes(svg,w,h,x,y,xTitle,yTitle,m){svg.append('rect').attr('data-chart-frame','').attr('x',m.left).attr('y',m.top).attr('width',w-m.left-m.right).attr('height',h-m.top-m.bottom);svg.append('g').attr('class','grid').attr('transform',`translate(${m.left},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(w-m.left-m.right)).tickFormat(''));svg.append('g').attr('class','axis').attr('transform',`translate(0,${h-m.bottom})`).call(d3.axisBottom(x).ticks(w<520?4:7));svg.append('g').attr('class','axis').attr('transform',`translate(${m.left},0)`).call(d3.axisLeft(y).ticks(5));svg.append('text').attr('class','axis-title').attr('data-axis','x').attr('x',(m.left+w-m.right)/2).attr('y',h-10).attr('text-anchor','middle').text(xTitle);svg.append('text').attr('class','axis-title').attr('data-axis','y').attr('transform','rotate(-90)').attr('x',-(m.top+h-m.bottom)/2).attr('y',17).attr('text-anchor','middle').text(yTitle);}
function labelledScatter(hostSel,height,xGet,yGet,xTitle,yTitle,key,aria,xFmt,yFmt){const {svg,w}=base(hostSel,height,aria),m={top:25,right:35,bottom:58,left:72};const xv=rows.map(xGet),yv=rows.map(yGet);const xp=(d3.max(xv)-d3.min(xv)||1)*.09,yp=(d3.max(yv)-d3.min(yv)||1)*.12;const x=d3.scaleLinear().domain([d3.min(xv)-xp,d3.max(xv)+xp]).nice().range([m.left,w-m.right]);const y=d3.scaleLinear().domain([d3.min(yv)-yp,d3.max(yv)+yp]).nice().range([height-m.bottom,m.top]);axes(svg,w,height,x,y,xTitle,yTitle,m);const nodes=rows.map(d=>({d,ax:x(xGet(d)),ay:y(yGet(d))}));nodes.forEach((n,i)=>{n.lx=n.ax+(i%2?8:-8);n.ly=n.ay+(i%3-1)*12});for(let k=0;k<90;k++){for(const n of nodes){n.lx+=(n.ax-n.lx)*.08;n.ly+=(n.ay-11-n.ly)*.08;}for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j],dx=a.lx-b.lx,dy=a.ly-b.ly;if(Math.abs(dx)<21&&Math.abs(dy)<13){const push=(13-Math.abs(dy))*.18*(dy>=0?1:-1);a.ly+=push;b.ly-=push;}}}const g=svg.append('g');g.selectAll('line').data(nodes).join('line').attr('class','leader').attr('x1',n=>n.ax).attr('y1',n=>n.ay).attr('x2',n=>n.lx).attr('y2',n=>n.ly+3);g.selectAll('circle').data(nodes).join('circle').attr('cx',n=>n.ax).attr('cy',n=>n.ay).attr('r',n=>red(n.d,key)?5:3.5).attr('fill',n=>color(n.d,key)).attr('data-tooltip',n=>`${n.d.task_id}：${xTitle} ${xFmt(xGet(n.d))}；${yTitle} ${yFmt(yGet(n.d))}；面板异常度 ${n.d[key].toFixed(3)}`);g.selectAll('text').data(nodes).join('text').attr('class','task-label').attr('x',n=>n.lx).attr('y',n=>n.ly).attr('text-anchor','middle').attr('fill',n=>red(n.d,key)?'var(--red)':'var(--foreground)').text(n=>shortId(n.d));}
function stripPanel(hostSel,metrics,key,aria){const height=440,{svg,w}=base(hostSel,height,aria),m={top:18,right:35,bottom:55,left:145};const all=rows.flatMap(d=>metrics.map(q=>q.get(d))),ext=d3.extent(all),pad=(ext[1]-ext[0])*.08;const x=d3.scaleLinear().domain([ext[0]-pad,ext[1]+pad]).nice().range([m.left,w-m.right]);const y=d3.scaleBand().domain(metrics.map(q=>q.label)).range([m.top,height-m.bottom]).padding(.25);svg.append('rect').attr('data-chart-frame','').attr('x',m.left).attr('y',m.top).attr('width',w-m.left-m.right).attr('height',height-m.top-m.bottom);if(x.domain()[0]<0&&x.domain()[1]>0)svg.append('line').attr('class','zero').attr('x1',x(0)).attr('x2',x(0)).attr('y1',m.top).attr('y2',height-m.bottom);svg.append('g').attr('class','axis').attr('transform',`translate(0,${height-m.bottom})`).call(d3.axisBottom(x).ticks(w<520?4:7));svg.append('g').attr('class','axis').attr('transform',`translate(${m.left},0)`).call(d3.axisLeft(y).tickSize(0));svg.append('text').attr('class','axis-title').attr('data-axis','x').attr('x',(m.left+w-m.right)/2).attr('y',height-10).attr('text-anchor','middle').text('同题型内 z-score');for(const q of metrics){const yc=y(q.label)+y.bandwidth()/2;const ordered=[...rows].sort((a,b)=>q.get(a)-q.get(b));const lane=[-25,-12,1,14,27];const marks=svg.append('g').selectAll('g').data(ordered).join('g').attr('transform',(d,i)=>`translate(${x(q.get(d))},${yc+lane[i%5]})`);marks.append('circle').attr('r',d=>red(d,key)?5:3.5).attr('fill',d=>color(d,key)).attr('data-tooltip',d=>`${d.task_id} · ${q.label}: ${q.get(d).toFixed(3)} z；面板异常度 ${d[key].toFixed(3)}`);marks.append('text').attr('class','task-label').attr('x',0).attr('y',-7).attr('text-anchor','middle').attr('fill',d=>red(d,key)?'var(--red)':'var(--foreground)').text(shortId);}}
function draw(){labelledScatter('#sd-composite',390,d=>d.text_anomaly,d=>d.hidden_anomaly,'文字特征异常度（RMS z）','隐藏状态异常度（RMS z）','combined_anomaly','文字与隐藏状态综合偏离同题型中心',d3.format('.2f'),d3.format('.2f'));stripPanel('#sd-text',[{label:'输出 token 数',get:d=>d.z_visible_generated_tokens},{label:'验证表述次数',get:d=>d.z_verification_mentions||0},{label:'不确定/冲突表述次数',get:d=>d.z_uncertainty_mentions||0},{label:'未体现/不适用表述次数',get:d=>d.z_absence_mentions||0}],'text_anomaly','文字输出四项特征标准化分布');stripPanel('#sd-hidden',[{label:'平均相邻 token 漂移',get:d=>d.z_temporal_distance_mean},{label:'末段/前段漂移比',get:d=>d.z_temporal_terminal_to_early_ratio},{label:'后 8 层平均变化',get:d=>d.z_late8_depth_update_mean},{label:'后 8 层末段变化',get:d=>d.z_late8_depth_update_terminal}],'hidden_anomaly','隐藏状态四项变化特征标准化分布');labelledScatter('#sd-recurrence',400,d=>d.mean_nonlocal_max_cosine,d=>d.rate_above_threshold,'非局部最大余弦相似度均值','高复现位置比例（cos > 0.95）','recurrence_anomaly','最后层隐藏状态非局部复现分布',d3.format('.3f'),d3.format('.1%'));}
draw();new ResizeObserver(draw).observe(root);
})();
</script>
'''
OUT.write_text(fragment.replace('__DATA__', compact), encoding='utf-8')
print(OUT)
