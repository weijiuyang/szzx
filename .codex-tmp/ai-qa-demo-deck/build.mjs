import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT="/Users/szzx/szzx/二奢AI经营问答-Demo完整工作流.pptx";
const TMP="/Users/szzx/szzx/.codex-tmp/ai-qa-demo-deck/rendered";
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:"#101828",muted:"#667085",panel:"#F2F4F7",rule:"#D0D5DD",blue:"#3D8DFF",light:"#D9F0FF",green:"#DDF5E5",amber:"#FFF0C7",pink:"#FCE7EA",white:"#FFFFFF",black:"#000000",red:"#F04438"};
const FONT="PingFang SC";
function box(s,name,x,y,w,h,fill="none",line="none",round=false){return s.shapes.add({geometry:round?"roundRect":"rect",name,position:{left:x,top:y,width:w,height:h},fill,line:{style:"solid",fill:line,width:line==="none"?0:1}})}
function tx(s,name,text,x,y,w,h,size=22,o={}){const z=s.shapes.add({geometry:"textbox",name,position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:"solid",fill:"none",width:0}});z.text=text;z.text.style={fontSize:size,typeface:o.font||FONT,color:o.color||C.ink,bold:!!o.bold,alignment:o.align||"left",verticalAlignment:o.valign||"top",autoFit:o.autoFit||"shrinkText"};return z}
function title(s,text,n){tx(s,`title-${n}`,text,42,34,1165,72,38,{bold:true});tx(s,`page-${n}`,String(n).padStart(2,"0"),1180,665,55,22,14,{color:C.muted,align:"right"})}
function note(s,body){s.speakerNotes.textFrame.setText(`${body}\n\n[Sources]\n- 用户提出的产品设想；本页为概念 Demo，数据与界面均为示例。\n[/Sources]`)}
function conn(s,name,x,y,w,h=0,color=C.ink,width=2,arrow=true){s.shapes.add({geometry:"straightConnector1",name,position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:"solid",fill:color,width,...(arrow?{endArrowType:"triangle"}:{})}})}
function chip(s,name,text,x,y,w,fill=C.panel,color=C.ink){box(s,`${name}-b`,x,y,w,34,fill,"none",true);tx(s,name,text,x+8,y+7,w-16,20,15,{bold:true,align:"center",color})}

// 1 cover
{
 const s=p.slides.add();s.background.fill=C.white;
 tx(s,"eyebrow","未来产品 Demo｜完整工作流程",42,42,520,35,18,{color:C.muted,bold:true});
 tx(s,"cover","二奢 AI\n经营问答",42,180,720,180,66,{bold:true});
 tx(s,"cover-sub","像 ChatGPT 一样提问，\n但答案来自真实数据、多个 Agent 和可追溯的计算过程。",42,430,800,125,28,{color:C.muted});
 box(s,"right",1000,42,238,586,C.black,"none",false);tx(s,"right-t","ASK\nPLAN\nQUERY\nVERIFY\nANSWER",1032,145,175,330,28,{color:C.white,bold:true,align:"center",valign:"middle"});
 note(s,"开场：产品入口是熟悉的对话框，但核心能力不是聊天，而是把问题转成一套可验证的数据任务，最后渲染成结论、指标、证据和建议。");
}

// 2 scenario
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"Demo 从一个真实经营问题开始",2);
 tx(s,"boss","老板提问",42,145,200,35,19,{color:C.muted,bold:true});
 box(s,"question",42,195,1196,105,C.black,"none",true);tx(s,"question-t","“最近 30 天，抖音和百度哪个投放效果更好？为什么？”",70,224,1140,55,33,{color:C.white,bold:true,align:"center"});
 const xs=[42,342,642,942],heads=["一句话结论","关键指标","数据证据","AI 建议"],bodies=["哪个更好，依据是什么","投放、有效线索、到店、回收成交","查询了什么、口径是什么、数据是否完整","预算怎么调、观察多久、风险是什么"],fills=[C.light,C.panel,C.green,C.amber];
 for(let i=0;i<4;i++){box(s,`target-${i}`,xs[i],370,255,205,fills[i],"none",false);tx(s,`th-${i}`,heads[i],xs[i]+22,405,211,40,25,{bold:true,align:"center"});tx(s,`tb-${i}`,bodies[i],xs[i]+22,475,211,72,18,{color:C.muted,align:"center"});}
 tx(s,"demo-label","以下所有数字均为演示数据，重点展示产品如何工作。",200,625,880,35,21,{color:C.blue,bold:true,align:"center"});
 note(s,"说明演示目标：不是仅返回一段文字，而是同时返回结论、数据窗口、过程追踪与建议。");
}

// 3 full workflow
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"一次问答在后台会走完 8 个节点",3);
 const nodes=[
  ["1 接收问题","聊天窗口",42,160,C.light],["2 理解意图","时间、平台、指标",342,160,C.panel],["3 读取记忆","口径、权限、偏好",642,160,C.amber],["4 制定计划","拆成多个任务",942,160,C.green],
  ["5 调用 Agent","SQL / 指标 / 质量",942,430,C.green],["6 查询与计算","读取数据并聚合",642,430,C.light],["7 验证与解释","交叉校验、找原因",342,430,C.amber],["8 前端渲染","回答、卡片、建议",42,430,C.pink]
 ];
 // connectors first
 conn(s,"c1",282,225,60);conn(s,"c2",582,225,60);conn(s,"c3",882,225,60);conn(s,"c4",1060,300,0,130);
 // Remaining lower-row connectors point visually toward the left via arrowheads omitted; step numbering preserves order.
 conn(s,"lower1",882,495,60,0,C.ink,2,false);conn(s,"lower2",582,495,60,0,C.ink,2,false);conn(s,"lower3",282,495,60,0,C.ink,2,false);
 for(const [h,b,x,y,f] of nodes){box(s,`node-${h}`,x,y,240,130,f,C.rule,true);tx(s,`nh-${h}`,h,x+18,y+22,204,34,22,{bold:true,align:"center"});tx(s,`nb-${h}`,b,x+18,y+76,204,30,17,{color:C.muted,align:"center"});}
 tx(s,"flow-note","每个节点都有状态：等待、运行、成功、需要确认或失败；前端可以实时显示进度。",120,625,1040,38,22,{bold:true,align:"center"});
 note(s,"总览整条链路。真实实现时，各节点可由一个编排器管理；简单问题只走部分节点，复杂问题才调用更多 Agent。");
}

// 4 understanding + memory
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"第 1 步：模型先把自然语言变成结构化任务",4);
 box(s,"input",42,150,520,410,C.panel,"none",false);tx(s,"input-h","原始问题",70,180,180,35,24,{bold:true});tx(s,"input-q","最近 30 天，\n抖音和百度哪个投放效果更好？\n为什么？",70,255,440,150,30,{bold:true});
 box(s,"parsed",620,150,618,410,C.light,"none",false);tx(s,"parsed-h","解析结果",650,180,200,35,24,{bold:true});
 const parsed=["时间范围：最近 30 天","比较对象：抖音、百度","分析目标：投放效果","默认口径：回收成交成本 + 最终毛利","输出要求：结论、原因、建议、证据"];
 parsed.forEach((v,i)=>tx(s,`pv-${i}`,`• ${v}`,650,245+i*52,535,32,21,{color:C.muted}));
 box(s,"memory",160,590,960,52,C.amber,"none",true);tx(s,"memory-t","读取企业记忆：老板已要求“不要只看线索成本，优先看回收成交和销售毛利”。",180,603,920,28,20,{bold:true,align:"center"});
 note(s,"意图解析不直接查库。它先确定时间、对象、目标指标和输出形式，并读取经过确认的企业记忆。如果问题存在歧义，系统应先追问。");
}

// 5 agent plan
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"第 2 步：编排器把问题拆给不同 Agent",5);
 const xs=[42,342,642,942],heads=["Schema Agent","Text-to-SQL Agent","Metric Agent","Quality Agent"],subs=["找到可用数据域与字段含义","生成只读查询并控制范围","按公司口径计算指标","检查缺失、重复与异常"],fills=[C.panel,C.light,C.green,C.amber];
 for(let i=0;i<4;i++){box(s,`agent-${i}`,xs[i],190,255,280,fills[i],"none",false);chip(s,`status-${i}`,i===0?"已完成":i===1?"运行中":"等待中",xs[i]+72,215,110,i===0?C.green:i===1?C.light:C.white);tx(s,`agent-h-${i}`,heads[i],xs[i]+18,295,219,42,23,{bold:true,align:"center"});tx(s,`agent-b-${i}`,subs[i],xs[i]+20,385,215,58,17,{color:C.muted,align:"center"});}
 box(s,"plan",42,525,1196,85,C.black,"none",false);tx(s,"plan-t","执行计划：先确认可查询数据 → 并行生成查询与指标口径 → 校验结果 → 合并解释。",70,550,1140,40,24,{color:C.white,bold:true,align:"center"});
 note(s,"Agent 不是四个会聊天的人，而是四种受约束的能力。编排器负责先后顺序、并行执行、超时和失败重试。");
}

// 6 text-to-sql + abstract data
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"第 3 步：Text-to-SQL 只读查询抽象的数据域",6);
 box(s,"sql-window",42,145,660,455,"#111827","none",true);tx(s,"sql-label","TEXT → SQL｜生成并执行（示意）",70,170,450,30,18,{color:"#98A2B3",bold:true});
 tx(s,"sql","SELECT channel,\n       SUM(spend) AS spend,\n       COUNT(valid_lead) AS valid_leads,\n       COUNT(recycle_order) AS recycle_orders,\n       SUM(final_margin) AS margin\nFROM business_view\nWHERE date >= :last_30_days\n  AND channel IN ('抖音','百度')\nGROUP BY channel;",75,225,580,315,20,{font:"Menlo",color:C.white});
 const ds=[["投放数据域","消耗、计划、平台",770,165,C.light],["客户链路域","线索、预约、到店",980,165,C.panel],["交易数据域","回收、库存、销售",770,365,C.green],["组织权限域","部门、人员、范围",980,365,C.amber]];
 for(const [h,b,x,y,f] of ds){box(s,`ds-${h}`,x,y,190,155,f,"none",false);tx(s,`dsh-${h}`,h,x+15,y+25,160,35,21,{bold:true,align:"center"});tx(s,`dsb-${h}`,b,x+15,y+88,160,35,17,{color:C.muted,align:"center"});}
 tx(s,"sql-guard","安全护栏：只读、限定时间范围、限定可访问对象、执行前估算成本、记录查询日志。",160,630,960,34,20,{bold:true,align:"center"});
 note(s,"SQL 只是示意，真正系统可以查询数据仓库、API 或预先定义的业务视图。模型不直接接触数据库账号，所有查询经过权限和成本控制。");
}

// 7 merge results
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"第 4 步：Agent 结果先校验，再交给模型解释",7);
 const ys=[150,260,370,480],heads=["SQL 结果","指标计算","数据质量","原因分析"],vals=["返回 2 个渠道、30 天数据","计算回收成交成本、投放 ROI、最终毛利","完整率 97%；发现 2 天销售毛利尚未回传","百度到店率更高；抖音在线索→预约环节流失较大"],fills=[C.light,C.green,C.amber,C.panel];
 for(let i=0;i<4;i++){box(s,`result-${i}`,42,ys[i],1196,82,fills[i],"none",false);tx(s,`rh-${i}`,heads[i],70,ys[i]+20,180,36,23,{bold:true});tx(s,`rv-${i}`,vals[i],280,ys[i]+20,900,36,21,{color:C.muted});}
 box(s,"confidence",42,600,1196,55,C.black,"none",false);tx(s,"confidence-t","答案置信状态：可回答，但必须提示“销售毛利数据存在 2 天延迟”。",70,613,1140,30,22,{color:C.white,bold:true,align:"center"});
 note(s,"模型不是拿到第一份查询结果就回答。系统需要合并 SQL、指标、质量和原因分析结果，并决定是否可以回答、是否需要提示限制、是否应要求人工确认。");
}

// 8 final frontend UI mockup
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"第 5 步：前端把答案渲染成“结论 + 数据 + 建议 + 过程”",8);
 // app frame
 box(s,"app",42,125,1196,515,C.white,C.rule,true);box(s,"sidebar",42,125,180,515,"#111827","none",true);tx(s,"logo","经营大脑",70,155,120,35,22,{color:C.white,bold:true});
 tx(s,"nav","新对话\n\n历史分析\n企业记忆\n指标中心",70,235,110,220,18,{color:"#D0D5DD"});
 // chat header/question
 tx(s,"app-title","投放效果分析",250,150,300,34,22,{bold:true});chip(s,"demo-chip","演示数据",1080,148,110,C.amber);
 box(s,"q-bubble",250,205,900,52,C.panel,"none",true);tx(s,"q-text","最近 30 天，抖音和百度哪个投放效果更好？为什么？",275,219,850,26,18,{bold:true});
 // conclusion
 box(s,"conclusion",250,280,580,95,C.light,"none",false);tx(s,"conclusion-h","结论",270,296,80,25,17,{color:C.muted,bold:true});tx(s,"conclusion-v","百度当前综合效果更好",270,330,520,30,25,{bold:true});
 box(s,"advice",850,280,340,95,C.green,"none",false);tx(s,"advice-h","AI 建议",870,296,120,25,17,{color:C.muted,bold:true});tx(s,"advice-v","转移 10% 测试预算，观察两周",870,330,290,30,19,{bold:true});
 // KPI cards
 const kx=[250,465,680],kh=["回收成交成本","有效线索成本","最终毛利"],kv=["百度低 18%","抖音低 22%","百度高 14%"];
 for(let i=0;i<3;i++){box(s,`kpi-${i}`,kx[i],400,195,80,C.white,C.rule,true);tx(s,`kph-${i}`,kh[i],kx[i]+12,412,171,22,16,{color:C.muted,align:"center"});tx(s,`kpv-${i}`,kv[i],kx[i]+12,446,171,24,19,{bold:true,align:"center"});}
 // data trace
 box(s,"trace",900,400,290,150,"#111827","none",true);tx(s,"trace-h","过程追踪",920,416,160,24,17,{color:C.white,bold:true});tx(s,"trace-v","✓ 4 个 Agent 完成\n✓ 查询 3 个数据域\n! 毛利数据延迟 2 天\n查看 SQL 与指标口径 →",920,452,235,90,15,{color:"#D0D5DD"});
 box(s,"followup",250,510,625,80,C.amber,"none",false);tx(s,"followup-t","主要原因：百度到店率更高；抖音在线索到预约环节流失较大。",270,532,585,35,18,{bold:true});
 note(s,"这是最终产品界面示意：保留聊天体验，同时用结构化组件呈现结论、指标、建议、数据限制和过程追踪。用户可以展开查看 SQL、指标口径和原始记录。");
}

// 9 principles architecture
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"它的原理：五层共同完成一次可信问答",9);
 const layers=[
  ["交互层","对话、卡片、图表、过程窗口",C.light],
  ["编排层","意图理解、任务规划、Agent 调度、状态管理",C.panel],
  ["智能层","Text-to-SQL、指标计算、原因分析、建议生成",C.green],
  ["业务语义层","对象、关系、指标口径、企业记忆、权限",C.amber],
  ["数据与系统层","数据库、数据仓库、CRM、ERP、外部平台 API",C.pink]
 ];
 layers.forEach((v,i)=>{const y=135+i*95;box(s,`layer-${i}`,120,y,1040,70,v[2],"none",false);tx(s,`lh-${i}`,v[0],150,y+18,220,34,23,{bold:true});tx(s,`lb-${i}`,v[1],400,y+18,700,34,20,{color:C.muted});});
 tx(s,"principle","大模型只占其中一层；真正决定可信度的是业务语义、数据质量、权限和验证机制。",120,635,1040,35,22,{bold:true,align:"center"});
 note(s,"用五层说明原理。前端不是直接请求大模型，而是请求问答编排服务；编排服务根据业务语义调用工具和数据，最后返回可渲染的结构化结果。");
}

// 10 memory governance
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"记忆、权限和审计让系统越用越懂公司，但不越界",10);
 const xs=[42,342,642,942],heads=["企业记忆","用户偏好","权限边界","审计记录"],bodies=["部门职责、指标口径、经营规则","老板关注什么、常用时间范围、展示偏好","谁能查哪些对象、能否看客户明细、能否执行动作","问了什么、调用什么 Agent、查询什么、如何得出结论"],fills=[C.light,C.panel,C.amber,C.green];
 for(let i=0;i<4;i++){box(s,`gov-${i}`,xs[i],185,255,340,fills[i],"none",false);tx(s,`gh-${i}`,heads[i],xs[i]+22,220,211,42,25,{bold:true,align:"center"});tx(s,`gb-${i}`,bodies[i],xs[i]+22,330,211,120,18,{color:C.muted,align:"center"});}
 box(s,"memory-rule",42,565,1196,72,C.black,"none",false);tx(s,"memory-rule-t","不是所有聊天都自动成为记忆：关键规则需要确认、版本化，并允许管理员修改或撤销。",70,583,1140,38,22,{color:C.white,bold:true,align:"center"});
 note(s,"企业记忆需要治理。业务事实仍以数据库为准；聊天内容只有在被确认后才成为规则；权限必须贯穿查询、计算、展示和行动全过程。");
}

// 11 MVP
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"第一版 MVP：先把一种问题做深、做可信",11);
 tx(s,"mvp-q","首个问题族",42,145,260,34,20,{color:C.muted,bold:true});tx(s,"mvp-big","投放渠道效果比较",42,195,560,55,34,{bold:true});
 const rows=[["支持提问","渠道比较、趋势变化、异常原因、部门下钻"],["支持工具","意图解析、企业记忆、Text-to-SQL、指标计算、质量校验"],["前端组件","结论卡、指标卡、简单图表、AI 建议、过程追踪窗口"],["安全要求","只读查询、角色权限、脱敏、SQL 审计、答案引用来源"],["成功标准","10 个高频问题稳定回答；数字可追溯；业务负责人认可口径"]];
 rows.forEach((r,i)=>{const y=285+i*67;box(s,`mvp-${i}`,42,y,1196,53,i===2?C.light:C.panel,"none",false);tx(s,`mh-${i}`,r[0],65,y+13,170,28,19,{bold:true});tx(s,`mb-${i}`,r[1],255,y+13,930,28,18,{color:C.muted});});
 box(s,"next",42,640,1196,42,C.black,"none",false);tx(s,"next-t","下一步：确定首批 10 个问题、默认指标口径、可用数据范围和前端原型。",65,649,1150,25,20,{color:C.white,bold:true,align:"center"});
 note(s,"收尾明确第一版范围：不要一开始回答所有经营问题。先把投放渠道比较做成稳定闭环，再复制到部门表现、门店回收和库存销售问题。");
}

await fs.mkdir(TMP,{recursive:true});
for(const [i,s] of p.slides.items.entries()){const png=await p.export({slide:s,format:"png",scale:1});await fs.writeFile(`${TMP}/slide-${i+1}.png`,new Uint8Array(await png.arrayBuffer()));const lay=await s.export({format:"layout"});await fs.writeFile(`${TMP}/slide-${i+1}.layout.json`,await lay.text())}
const deck=await PresentationFile.exportPptx(p);await deck.save(OUT);console.log(OUT);
