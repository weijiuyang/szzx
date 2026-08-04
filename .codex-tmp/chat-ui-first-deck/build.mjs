import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT="/Users/szzx/szzx/二奢AI经营问答-UI优先Demo-V2.pptx";
const TMP="/Users/szzx/szzx/.codex-tmp/chat-ui-first-deck/rendered";
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:"#202123",muted:"#6B7280",side:"#171717",side2:"#212121",panel:"#F7F7F8",line:"#E5E7EB",blue:"#E7F3FF",blue2:"#3D8DFF",green:"#E4F6EA",amber:"#FFF3D1",pink:"#FCE8EC",white:"#FFFFFF",black:"#000000",code:"#111827"};
const FONT="PingFang SC";
function box(s,n,x,y,w,h,fill="none",line="none",round=false){return s.shapes.add({geometry:round?"roundRect":"rect",name:n,position:{left:x,top:y,width:w,height:h},fill,line:{style:"solid",fill:line,width:line==="none"?0:1}})}
function tx(s,n,t,x,y,w,h,size=22,o={}){const z=s.shapes.add({geometry:"textbox",name:n,position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:"solid",fill:"none",width:0}});z.text=t;z.text.style={fontSize:size,typeface:o.font||FONT,color:o.color||C.ink,bold:!!o.bold,alignment:o.align||"left",verticalAlignment:o.valign||"top",autoFit:o.autoFit||"shrinkText"};return z}
function pill(s,n,t,x,y,w,fill=C.panel,color=C.ink){box(s,`${n}-box`,x,y,w,32,fill,"none",true);tx(s,n,t,x+8,y+7,w-16,18,14,{color,bold:true,align:"center"})}
function note(s,t){s.speakerNotes.textFrame.setText(`${t}\n\n[Sources]\n- 用户提出的产品设想；界面与数字均为原创概念 Demo。\n[/Sources]`)}
function title(s,t,n){tx(s,`title-${n}`,t,42,30,1160,66,37,{bold:true});tx(s,`page-${n}`,String(n).padStart(2,"0"),1180,665,55,20,13,{color:C.muted,align:"right"})}
function conn(s,n,x,y,w,h=0,arrow=true){s.shapes.add({geometry:"straightConnector1",name:n,position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:"solid",fill:C.ink,width:2,...(arrow?{endArrowType:"triangle"}:{})}})}

function appShell(s, active="新对话"){
 s.background.fill=C.white;
 box(s,"sidebar",0,0,255,720,C.side,"none",false);
 tx(s,"brand","智鉴 AI",28,25,150,35,22,{color:C.white,bold:true});pill(s,"new","＋ 新对话",20,78,215,C.side2,C.white);
 tx(s,"recent-label","最近",28,140,120,24,14,{color:"#9CA3AF",bold:true});
 const items=["投放渠道效果比较","本月部门经营体检","门店回收转化分析","库存商品异常" ];
 items.forEach((v,i)=>{if(v===active)box(s,`active-${i}`,18,175+i*50,219,40,"#2F2F2F","none",true);tx(s,`item-${i}`,v,32,186+i*50,190,22,15,{color:i===0?C.white:"#D1D5DB"})});
 tx(s,"memory-nav","企业记忆\n指标口径\n数据与权限",32,430,160,125,16,{color:"#D1D5DB"});
 box(s,"user",18,655,219,45,C.side2,"none",true);box(s,"avatar",30,665,26,26,"#6B7280","none",true);tx(s,"username","老板账号",68,668,120,22,15,{color:C.white,bold:true});
 box(s,"topbar",255,0,1025,58,C.white,C.line,false);tx(s,"model","经营分析助手  ▾",285,18,230,24,16,{bold:true});pill(s,"private","企业私有数据",1080,13,155,C.panel,C.muted);
}
function composer(s,text="向经营大脑提问……",send=false){box(s,"composer-shadow",405,612,725,76,C.white,C.line,true);tx(s,"attach","＋",430,638,25,25,22,{color:C.muted,bold:true,align:"center"});tx(s,"composer-text",text,475,634,560,28,18,{color:text.includes("提问")?"#9CA3AF":C.ink});box(s,"send",1065,627,44,44,send?C.black:"#D1D5DB","none",true);tx(s,"send-arrow","↑",1075,635,24,24,20,{color:C.white,bold:true,align:"center"});tx(s,"hint","AI 可能出错，重要经营决策请核对数据来源。",565,690,500,18,12,{color:"#9CA3AF",align:"center"});}

// 1 — actual product home first
{
 const s=p.slides.add();appShell(s,"新对话");
 box(s,"mark",713,165,76,76,C.black,"none",true);tx(s,"mark-t","智",728,181,46,42,28,{color:C.white,bold:true,align:"center"});
 tx(s,"welcome","今天想分析什么？",470,270,560,55,34,{bold:true,align:"center"});
 tx(s,"sub","直接问经营问题，我会查询企业数据并展示计算过程。",440,335,620,36,19,{color:C.muted,align:"center"});
 const prompts=[["比较投放渠道","抖音和百度哪个效果更好？"],["检查经营异常","哪个部门本月表现最差？"],["分析门店转化","到店多但回收少的原因是什么？"]];
 prompts.forEach((v,i)=>{const x=390+i*245;box(s,`prompt-${i}`,x,420,220,100,C.white,C.line,true);tx(s,`ph-${i}`,v[0],x+16,440,188,25,17,{bold:true});tx(s,`pb-${i}`,v[1],x+16,477,188,27,14,{color:C.muted})});
 composer(s);
 note(s,"新版第一眼就是完整产品首页：左侧会话历史，中间是对话入口，底部是输入框。先让听众理解这是一款可以直接提问的经营产品。");
}

// 2 — question submitted
{
 const s=p.slides.add();appShell(s,"投放渠道效果比较");
 tx(s,"thread-title","投放渠道效果比较",420,85,700,35,22,{bold:true});
 box(s,"user-msg",560,145,590,86,C.panel,"none",true);box(s,"user-avatar",1100,115,34,34,"#6B7280","none",true);tx(s,"user-a","老",1108,121,18,18,13,{color:C.white,bold:true,align:"center"});
 tx(s,"user-q","最近 30 天，抖音和百度哪个投放效果更好？为什么？",585,170,535,32,20,{bold:true});
 box(s,"ai-avatar",350,270,38,38,C.black,"none",true);tx(s,"ai-a","智",359,277,20,20,14,{color:C.white,bold:true,align:"center"});
 tx(s,"thinking","我会按公司的默认口径，优先比较回收成交成本和最终毛利。",410,274,720,31,18,{});
 box(s,"task",410,330,720,92,C.white,C.line,true);pill(s,"run","正在制定计划",430,348,125,C.blue);tx(s,"task-v","识别时间范围、比较渠道、加载指标口径和查询权限……",430,389,650,23,16,{color:C.muted});
 composer(s,"继续追问……");
 note(s,"第二页仍然保持同一个聊天产品界面。用户问题出现在对话里，系统先说明将使用什么经营口径，而不是立刻生成结论。");
}

// 3 — running agents + SQL artifact
{
 const s=p.slides.add();appShell(s,"投放渠道效果比较");
 tx(s,"thread-title","投放渠道效果比较",310,78,450,34,21,{bold:true});pill(s,"elapsed","已运行 6.8 秒",1040,75,145,C.panel,C.muted);
 box(s,"ai-avatar",290,135,36,36,C.black,"none",true);tx(s,"ai-a","智",298,142,20,20,13,{color:C.white,bold:true,align:"center"});tx(s,"status-head","正在分析企业数据",345,137,380,28,19,{bold:true});
 const steps=[["✓","理解问题与读取企业记忆","完成",C.green],["✓","Schema Agent：定位可查询的数据域","完成",C.green],["●","Text-to-SQL Agent：生成并执行只读查询","运行中",C.blue],["○","Metric Agent：计算回收成交成本与毛利","等待",C.panel],["○","Quality Agent：检查缺失、重复和延迟","等待",C.panel]];
 steps.forEach((v,i)=>{const y=190+i*52;box(s,`step-${i}`,345,y,500,40,C.white,C.line,true);tx(s,`icon-${i}`,v[0],360,y+10,25,20,15,{bold:true,align:"center",color:i<2?"#16A34A":i===2?C.blue2:C.muted});tx(s,`step-t-${i}`,v[1],398,y+10,360,20,15,{});pill(s,`step-s-${i}`,v[2],760,y+4,70,v[3],C.muted)});
 // right artifact drawer like Codex tool output
 box(s,"drawer",870,118,350,430,C.code,"none",true);tx(s,"drawer-h","Text-to-SQL",895,140,180,28,18,{color:C.white,bold:true});pill(s,"readonly","只读",1125,138,65,"#253047","#D1D5DB");
 tx(s,"sql","SELECT channel,\n  SUM(spend),\n  COUNT(valid_lead),\n  COUNT(recycle_order),\n  SUM(final_margin)\nFROM business_view\nWHERE date >= :last_30_days\n  AND channel IN ('抖音','百度')\nGROUP BY channel;",895,205,295,230,15,{font:"Menlo",color:"#E5E7EB"});
 tx(s,"dbs","查询数据域：投放、客户链路、交易\n权限范围：汇总级，不返回客户明细",895,465,295,55,13,{color:"#9CA3AF"});
 composer(s,"分析运行中，可继续补充条件……");
 note(s,"第三页是用户想看到的 Codex 式执行界面：左侧是 Agent 进度，右侧展开 Text-to-SQL 工具窗口。用户知道系统正在做什么、查什么以及当前权限范围。");
}

// 4 — final answer in chat UI
{
 const s=p.slides.add();appShell(s,"投放渠道效果比较");
 tx(s,"thread-title","投放渠道效果比较",290,70,450,34,21,{bold:true});pill(s,"demo","演示数据",1080,70,110,C.amber,C.muted);
 box(s,"ai-avatar",290,120,36,36,C.black,"none",true);tx(s,"ai-a","智",298,127,20,20,13,{color:C.white,bold:true,align:"center"});
 tx(s,"answer-head","百度当前综合投放效果更好。",345,118,620,34,24,{bold:true});tx(s,"answer-sub","百度线索成本较高，但回收成交成本更低，最终毛利更高。",345,158,750,28,17,{color:C.muted});
 // comparison chart area
 box(s,"chart",345,210,510,210,C.white,C.line,true);tx(s,"chart-h","关键指标对比",365,228,180,25,17,{bold:true});
 const bars=[["有效线索成本",62,100],["回收成交成本",100,82],["最终毛利",75,100]];
 bars.forEach((v,i)=>{const y=275+i*43;tx(s,`lab-${i}`,v[0],365,y,120,22,13,{color:C.muted});box(s,`dy-${i}`,500,y+2,v[1]*2.1,14,"#B8DDFB","none",true);box(s,`bd-${i}`,500,y+20,v[2]*2.1,14,C.blue2,"none",true)});
 tx(s,"legend","抖音   ■   百度   ■",650,390,180,18,12,{color:C.muted,align:"right"});
 // right insight
 box(s,"suggest",880,210,300,95,C.green,"none",true);tx(s,"suggest-h","AI 建议",900,225,100,24,15,{color:C.muted,bold:true});tx(s,"suggest-v","将抖音 10% 预算转入百度测试，观察两周。",900,258,250,35,17,{bold:true});
 box(s,"quality",880,325,300,95,C.amber,"none",true);tx(s,"quality-h","数据提示",900,340,100,24,15,{color:C.muted,bold:true});tx(s,"quality-v","销售毛利数据存在 2 天延迟。",900,373,250,28,17,{bold:true});
 box(s,"why",345,445,835,75,C.panel,"none",true);tx(s,"why-h","主要原因",365,460,90,22,15,{color:C.muted,bold:true});tx(s,"why-v","百度到店率更高；抖音在线索 → 预约环节流失较大。",475,460,670,28,17,{bold:true});
 pill(s,"trace","查看 4 个 Agent",345,545,145,C.panel,C.muted);pill(s,"sql-link","查看 SQL",505,545,105,C.panel,C.muted);pill(s,"metric","查看指标口径",625,545,135,C.panel,C.muted);pill(s,"source","打开数据来源",775,545,135,C.panel,C.muted);
 composer(s,"继续追问，例如：抖音哪个计划拖累最大？",true);
 note(s,"第四页在同一个对话窗口里返回可交互结果：自然语言结论、对比图、AI 建议、数据质量提示、原因解释，以及 Agent、SQL、指标口径和数据来源入口。");
}

// 5 workflow after UI
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"看完界面，再拆解后台走过的完整链路",5);
 const nodes=[["提问","聊天窗口",42,190,C.blue],["理解","意图 + 记忆",242,190,C.panel],["计划","任务编排",442,190,C.amber],["执行","Agent + 工具",642,190,C.green],["验证","质量 + 口径",842,190,C.amber],["渲染","答案组件",1042,190,C.pink]];
 for(let i=0;i<5;i++)conn(s,`c-${i}`,202+i*200,255,40);
 nodes.forEach((v,i)=>{box(s,`n-${i}`,v[2],v[3],160,130,v[4],C.line,true);tx(s,`nh-${i}`,v[0],v[2]+15,v[3]+25,130,32,24,{bold:true,align:"center"});tx(s,`nb-${i}`,v[1],v[2]+10,v[3]+78,140,28,16,{color:C.muted,align:"center"})});
 box(s,"loop",120,430,1040,105,C.black,"none",false);tx(s,"loop-t","每个节点都返回结构化状态和结果；前端根据状态决定展示“运行中、需要确认、失败或完成”。",160,458,960,52,23,{color:C.white,bold:true,align:"center"});
 tx(s,"after-ui","界面只是入口；可信答案来自整个链路的共同协作。",240,600,800,35,24,{bold:true,align:"center"});
 note(s,"第五页才开始解释流程。强调前端不会直接调用大模型，而是把问题交给编排器，再由编排器调用 Agent、数据和验证机制。");
}

// 6 agent principle
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"Agent 是受约束的专业能力，不是多个随意聊天的模型",6);
 const xs=[42,342,642,942],heads=["Schema Agent","Text-to-SQL Agent","Metric Agent","Quality Agent"],bodies=["定位数据域\n解释字段语义","生成只读查询\n控制时间与范围","按公司口径计算\n回收成本与毛利","检查缺失、重复\n延迟与异常"],fills=[C.panel,C.blue,C.green,C.amber];
 for(let i=0;i<4;i++){box(s,`agent-${i}`,xs[i],180,255,330,fills[i],"none",false);pill(s,`cap-${i}`,i===0?"理解数据":i===1?"查询数据":i===2?"计算指标":"验证结果",xs[i]+65,205,125,C.white,C.muted);tx(s,`ah-${i}`,heads[i],xs[i]+15,295,225,40,22,{bold:true,align:"center"});tx(s,`ab-${i}`,bodies[i],xs[i]+20,395,215,75,18,{color:C.muted,align:"center"});}
 box(s,"orchestrator",42,550,1196,72,C.black,"none",false);tx(s,"orchestrator-t","编排器决定调用顺序、并行执行、失败重试，以及哪些结果可以进入最终答案。",72,570,1140,34,22,{color:C.white,bold:true,align:"center"});
 note(s,"说明 Agent 的边界。每个 Agent 只负责一类任务，并且拥有有限工具和明确输出格式；编排器负责控制流程。");
}

// 7 text-to-sql principle
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"Text-to-SQL 不是让模型随便查库，而是生成受控查询",7);
 box(s,"sql",42,145,600,430,C.code,"none",true);tx(s,"sql-h","生成的查询（示意）",70,170,250,27,18,{color:"#9CA3AF",bold:true});tx(s,"sql-t","SELECT channel,\n       SUM(spend),\n       COUNT(valid_lead),\n       COUNT(recycle_order),\n       SUM(final_margin)\nFROM business_view\nWHERE date >= :last_30_days\n  AND channel IN ('抖音','百度')\nGROUP BY channel;",75,225,520,275,18,{font:"Menlo",color:C.white});
 const guards=[["只读","禁止修改业务数据"],["权限","只查询用户可见对象"],["范围","限定时间、行数和成本"],["语义","优先使用已定义业务视图"],["审计","保存 SQL、耗时与返回规模"]];
 guards.forEach((v,i)=>{const y=145+i*88;box(s,`g-${i}`,700,y,538,70,i===1?C.amber:C.panel,"none",false);tx(s,`gh-${i}`,v[0],730,y+18,100,30,21,{bold:true});tx(s,`gb-${i}`,v[1],860,y+18,330,30,18,{color:C.muted})});
 tx(s,"sql-note","SQL、API 调用或预定义指标服务都可以是工具；前端统一展示执行证据。",150,620,980,35,22,{bold:true,align:"center"});
 note(s,"原理页说明 Text-to-SQL 的安全机制。真正实现中可以优先访问稳定业务视图，而不是暴露全部原始表。");
}

// 8 architecture
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"产品由五层组成，大模型只是其中一层",8);
 const rows=[["界面层","聊天、会话历史、输入框、工具过程、答案卡片",C.blue],["编排层","问题理解、计划、Agent 调度、状态管理",C.panel],["智能工具层","Text-to-SQL、指标计算、原因分析、建议生成",C.green],["业务语义层","对象关系、指标口径、企业记忆、权限规则",C.amber],["数据系统层","数据库、数据仓库、CRM、ERP、平台 API",C.pink]];
 rows.forEach((v,i)=>{const y=130+i*98;box(s,`layer-${i}`,120,y,1040,72,v[2],"none",false);tx(s,`lh-${i}`,v[0],155,y+20,200,32,22,{bold:true});tx(s,`lb-${i}`,v[1],390,y+20,710,32,19,{color:C.muted})});
 tx(s,"arch-note","界面负责让人理解；编排和业务语义负责让系统可信；数据层提供事实。",160,635,960,34,22,{bold:true,align:"center"});
 note(s,"架构页把界面放在第一层，与前四页呼应。系统不是前端直接连数据库，也不是前端直接把所有内容发给大模型。");
}

// 9 memory security
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"记忆、权限和审计，让对话产品越用越懂公司但不越界",9);
 const xs=[42,342,642,942],heads=["企业记忆","用户偏好","权限边界","审计记录"],bodies=["指标口径、部门职责、经营规则","老板常用范围、关注重点、展示方式","能看哪些对象、是否能看客户明细、能否执行动作","问题、Agent、SQL、计算口径和最终结论"],fills=[C.blue,C.panel,C.amber,C.green];
 for(let i=0;i<4;i++){box(s,`mem-${i}`,xs[i],180,255,350,fills[i],"none",false);tx(s,`mh-${i}`,heads[i],xs[i]+20,225,215,42,25,{bold:true,align:"center"});tx(s,`mb-${i}`,bodies[i],xs[i]+20,350,215,105,18,{color:C.muted,align:"center"});}
 box(s,"mem-rule",42,570,1196,65,C.black,"none",false);tx(s,"mem-rule-t","不是所有聊天都成为企业记忆：重要规则必须确认、版本化，并可修改或撤销。",70,587,1140,34,22,{color:C.white,bold:true,align:"center"});
 note(s,"记忆与安全页说明长期使用机制。业务事实仍以数据库为准，只有确认后的规则才能成为企业记忆。");
}

// 10 MVP
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"第一版先实现“看得见、查得到、说得清”",10);
 const goals=[["看得见","完整 ChatGPT/Codex 式对话界面\n实时 Agent 与工具进度\n结构化答案组件",C.blue],["查得到","一个投放分析问题族\n只读 Text-to-SQL\n可追溯数据与指标口径",C.green],["说得清","明确结论与原因\n数据质量提示\n可执行但不自动执行的 AI 建议",C.amber]];
 goals.forEach((v,i)=>{const x=42+i*411;box(s,`goal-${i}`,x,170,375,350,v[2],"none",false);tx(s,`goal-h-${i}`,v[0],x+30,210,315,52,31,{bold:true,align:"center"});tx(s,`goal-b-${i}`,v[1],x+30,320,315,130,20,{color:C.muted,align:"center"})});
 box(s,"next",42,575,1196,70,C.black,"none",false);tx(s,"next-t","下一步先画可点击前端原型，再确定首批 10 个问题、指标口径和可查询数据范围。",70,592,1140,36,22,{color:C.white,bold:true,align:"center"});
 note(s,"收尾明确下一步：这次先把产品界面讲清楚。项目进入实施时，应先做可点击原型，验证用户是否理解对话、过程和结果组件。");
}

await fs.mkdir(TMP,{recursive:true});
for(const [i,s] of p.slides.items.entries()){const png=await p.export({slide:s,format:"png",scale:1});await fs.writeFile(`${TMP}/slide-${i+1}.png`,new Uint8Array(await png.arrayBuffer()));const lay=await s.export({format:"layout"});await fs.writeFile(`${TMP}/slide-${i+1}.layout.json`,await lay.text())}
const deck=await PresentationFile.exportPptx(p);await deck.save(OUT);console.log(OUT);
