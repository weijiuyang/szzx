import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT="/Users/szzx/szzx/Palantir介绍与二奢智慧大脑启示.pptx";
const TMP="/Users/szzx/szzx/.codex-tmp/palantir-intro-deck/rendered";
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={ink:"#101828",muted:"#667085",panel:"#F2F4F7",rule:"#D0D5DD",blue:"#3D8DFF",light:"#D9F0FF",green:"#DDF5E5",amber:"#FFF0C7",pink:"#FCE7EA",white:"#FFFFFF",black:"#000000"};
const FONT="PingFang SC";

function box(s,name,x,y,w,h,fill="none",line="none",round=false){return s.shapes.add({geometry:round?"roundRect":"rect",name,position:{left:x,top:y,width:w,height:h},fill,line:{style:"solid",fill:line,width:line==="none"?0:1}})}
function tx(s,name,text,x,y,w,h,size=22,o={}){const z=s.shapes.add({geometry:"textbox",name,position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:"solid",fill:"none",width:0}});z.text=text;z.text.style={fontSize:size,typeface:FONT,color:o.color||C.ink,bold:!!o.bold,alignment:o.align||"left",verticalAlignment:o.valign||"top",autoFit:o.autoFit||"shrinkText"};return z}
function title(s,text,n){tx(s,`title-${n}`,text,42,34,1160,72,38,{bold:true});tx(s,`page-${n}`,String(n).padStart(2,"0"),1180,665,55,22,14,{color:C.muted,align:"right"})}
function note(s,body,sources=[]){s.speakerNotes.textFrame.setText(`${body}\n\n[Sources]\n${sources.map(x=>`- ${x}`).join("\n")}\n[/Sources]`)}
function line(s,x,y,w,color=C.rule,width=1){s.shapes.add({geometry:"straightConnector1",position:{left:x,top:y,width:w,height:0},fill:"none",line:{style:"solid",fill:color,width}})}

// 1 — Codex Grid sparse cover hierarchy
{
 const s=p.slides.add();s.background.fill=C.white;
 tx(s,"eyebrow","方法论介绍｜内部学习材料",42,42,500,34,18,{color:C.muted,bold:true});
 tx(s,"cover","Palantir",42,180,900,105,78,{bold:true});
 tx(s,"cover-cn","为什么它强调 Ontology，\n而不只是“大模型 + 数据库”",42,320,930,155,40,{bold:true});
 tx(s,"subtitle","理解一种把数据、业务关系、决策与行动连起来的方法。",42,545,900,50,25,{color:C.muted});
 box(s,"accent",1080,42,158,586,C.black,"none",false);tx(s,"accent-text","DATA\nLOGIC\nACTION\nSECURITY",1102,185,115,260,25,{color:C.white,bold:true,align:"center",valign:"middle"});
 note(s,"开场说明：本次不是做厂商采购介绍，而是学习 Palantir 的产品思想，帮助我们理解智慧经营大脑应该怎样落地。",["https://www.palantir.com/docs/foundry/ontology/why-ontology"]);
}

// 2
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"一句话理解：Palantir 想做企业的“经营操作系统”",2);
 tx(s,"not","它不只是",42,165,380,45,24,{color:C.muted,bold:true});
 tx(s,"not-list","数据库\nBI 看板\n大模型聊天机器人",42,225,420,210,35,{bold:true});
 line(s,540,145,0,C.rule,2);box(s,"divider",620,145,2,390,C.rule,"none",false);
 tx(s,"is","而是把",690,165,380,45,24,{color:C.muted,bold:true});
 tx(s,"is-list","数据\n分析与业务规则\n真实业务动作\n权限和审计",690,225,460,260,35,{bold:true});
 box(s,"bottom",42,570,1196,65,C.light,"none",false);tx(s,"bottom-t","组织在同一套业务语义中看事实、做决定、执行并记录结果。",70,584,1140,38,25,{bold:true,align:"center"});
 note(s,"官方将 AIP、Foundry、Apollo 的组合描述为企业操作系统；这里用非技术语言解释其目标。",["https://www.palantir.com/docs/foundry/architecture-center/platforms","https://www.palantir.com/platforms/"]);
}

// 3 — four topic silhouette
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"四个产品名称，解决的是不同层面的问题",3);
 const xs=[42,342,642,942],fills=[C.panel,C.light,C.green,C.amber],heads=["Gotham","Foundry","AIP","Apollo"],subs=["面向复杂任务的\n决策与行动平台","数据运营、Ontology、\n分析与工作流","让生成式 AI 安全连接\n企业数据与业务","跨环境持续部署和\n运行软件"];
 for(let i=0;i<4;i++){box(s,`platform-${i}`,xs[i],190,255,350,fills[i],"none",false);tx(s,`ph-${i}`,heads[i],xs[i]+25,225,205,55,31,{bold:true});tx(s,`ps-${i}`,subs[i],xs[i]+25,330,205,120,21,{color:C.muted});}
 tx(s,"platform-note","理解重点：对企业经营项目而言，Foundry 的 Ontology 与 AIP 的结合最值得借鉴。",100,600,1080,38,24,{bold:true,align:"center"});
 note(s,"Palantir 官方平台页列出 Gotham、Foundry、AIP、Apollo；当前标准架构强调 AIP、Foundry、Apollo 三个平台的集成。",["https://www.palantir.com/platforms/","https://www.palantir.com/docs/foundry/architecture-center/platforms"]);
}

// 4 — comparison
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"传统数据项目常停在“看见问题”，Palantir 强调闭环",4);
 tx(s,"left-h","传统分析链路",42,160,500,45,29,{bold:true});tx(s,"left-b","数据汇总\n→ 报表和看板\n→ 人工解释\n→ 线下通知执行\n→ 结果往往没有回到系统",42,230,500,290,25,{color:C.muted});
 tx(s,"right-h","Ontology 驱动的链路",670,160,520,45,29,{bold:true});tx(s,"right-b","数据变成业务对象\n→ 规则和模型辅助判断\n→ 授权用户或 AI 执行动作\n→ 写回业务系统\n→ 决策过程沉淀为下一次依据",670,230,520,290,25,{color:C.muted});
 box(s,"close-loop",42,565,1196,66,C.black,"none",false);tx(s,"close-loop-t","区别不只在分析能力，而在能否安全地改变业务状态并记录结果。",72,580,1130,36,24,{color:C.white,bold:true,align:"center"});
 note(s,"Palantir 官方将“关闭行动回路”视为操作系统区别于分析系统的关键；此页为对该观点的通俗转述。",["https://www.palantir.com/docs/foundry/ontology/why-ontology","https://www.palantir.com/platforms/foundry/"]);
}

// 5 — ontology simple diagram, connectors first
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"Ontology 的核心：对象是名词，动作是动词",5);
 const edges=[[245,270,330,270],[535,270,620,270],[825,270,910,270],[720,330,720,435]];
 for(const [x,y,x2,y2] of edges)s.shapes.add({geometry:"straightConnector1",position:{left:Math.min(x,x2),top:Math.min(y,y2),width:Math.abs(x2-x),height:Math.abs(y2-y)},fill:"none",line:{style:"solid",fill:C.ink,width:2,endArrowType:"triangle"}});
 const nodes=[["对象 Objects","客户、订单、商品、门店",42,205,C.light],["关系 Links","客户来自哪个平台\n商品属于哪个订单",330,205,C.panel],["动作 Actions","创建预约、调整预算\n确认回收、发出预警",620,205,C.green],["逻辑 Logic","指标、规则、模型",910,205,C.amber],["安全 Security","谁能看、谁能改、谁能批准；每次动作留下审计记录",510,435,C.pink]];
 for(const [h,b,x,y,f] of nodes){box(s,`on-${h}`,x,y,x===510?420:245,x===510?130:130,f,C.rule,true);tx(s,`oh-${h}`,h,x+20,y+18,x===510?380:205,34,24,{bold:true,align:"center"});tx(s,`ob-${h}`,b,x+20,y+62,x===510?380:205,x===510?52:55,18,{color:C.muted,align:"center"});}
 tx(s,"sentence","当“名词 + 关系 + 动词 + 逻辑 + 权限”连起来，数据才成为可行动的业务世界。",100,615,1080,38,23,{bold:true,align:"center"});
 note(s,"官方文档把对象和链接比作企业的名词，把动作比作动词；Ontology 还把数据、逻辑、动作与安全结合起来。",["https://www.palantir.com/docs/foundry/ontology/why-ontology","https://www.palantir.com/explore/platforms/foundry/ontology/","https://www.palantir.com/docs/foundry/getting-started/introductory-concepts"]);
}

// 6 — example flow
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"一个供应链例子：从异常信号走到真实调整",6);
 const labels=["数据源","业务对象","分析与规则","建议动作","执行写回"],texts=["ERP / CRM / 设备","工厂、产线、订单、库存","缺货风险、产能约束、预测模型","调整采购或配送策略","更新订单并记录审批"],fills=[C.panel,C.light,C.amber,C.green,C.pink];
 for(let i=0;i<4;i++)s.shapes.add({geometry:"straightConnector1",position:{left:250+i*238,top:340,width:50,height:0},fill:"none",line:{style:"solid",fill:C.ink,width:2,endArrowType:"triangle"}});
 for(let i=0;i<5;i++){const x=42+i*238;box(s,`ex-${i}`,x,220,208,250,fills[i],"none",false);tx(s,`ex-h-${i}`,labels[i],x+18,250,172,40,24,{bold:true,align:"center"});tx(s,`ex-b-${i}`,texts[i],x+18,340,172,90,18,{color:C.muted,align:"center"});}
 tx(s,"example-take","关键是：系统不仅告诉你“可能缺货”，还知道允许谁用什么动作解决。",100,590,1080,45,24,{bold:true,align:"center"});
 note(s,"Palantir 官方架构说明以供应链中的工厂、产线和客户订单为对象示例，并以更新采购订单、改变配送策略等作为动作示例。本页将其简化为一条闭环。",["https://www.palantir.com/docs/foundry/architecture-center/overview"]);
}

// 7
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"AIP 的价值：让大模型站在受控的业务世界之上",7);
 box(s,"llm",42,180,280,340,C.light,"none",false);tx(s,"llm-h","大模型",75,225,215,45,30,{bold:true,align:"center"});tx(s,"llm-b","理解自然语言\n生成解释和建议\n调用被授权的工具",75,330,215,120,21,{color:C.muted,align:"center"});
 box(s,"onto",500,150,280,400,C.black,"none",false);tx(s,"onto-h","Ontology",535,225,210,48,31,{bold:true,color:C.white,align:"center"});tx(s,"onto-b","对象与关系\n业务逻辑\n动作与权限\n完整审计",535,330,210,145,22,{color:C.white,align:"center"});
 box(s,"ops",958,180,280,340,C.green,"none",false);tx(s,"ops-h","真实业务",990,225,215,45,30,{bold:true,align:"center"});tx(s,"ops-b","查询事实\n提出行动\n执行或等待审批\n记录结果",990,330,215,145,21,{color:C.muted,align:"center"});
 s.shapes.add({geometry:"straightConnector1",position:{left:322,top:345,width:178,height:0},fill:"none",line:{style:"solid",fill:C.ink,width:2,endArrowType:"triangle"}});s.shapes.add({geometry:"straightConnector1",position:{left:780,top:345,width:178,height:0},fill:"none",line:{style:"solid",fill:C.ink,width:2,endArrowType:"triangle"}});
 tx(s,"aip-note","没有 Ontology，大模型容易只会“说”；有了受控对象和动作，才可能安全地“做”。",100,600,1080,40,24,{bold:true,align:"center"});
 note(s,"AIP 官方说明其把 AI 连接到组织数据和运营，并在安全、审计、资源管理框架内构建代理和自动化；此页是对该架构意义的解释。",["https://www.palantir.com/docs/foundry/aip","https://www.palantir.com/docs/foundry/object-permissioning/overview"]);
}

// 8 — three milestones
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"Palantir 的落地思路：从关键决策倒推，而不是先堆数据",8);
 line(s,95,350,1090,C.ink,2);const xs=[95,450,815],heads=["先找决策","再建最小本体","最后进入行动"],bodies=["哪一个高价值问题\n值得更快、更准地回答？","需要哪些对象、关系、指标、权限\n才能支持这个决策？","把建议、审批、写回和反馈\n放进真实工作流程。"];
 for(let i=0;i<3;i++){box(s,`dot-${i}`,xs[i],341,18,18,C.blue,"none",true);tx(s,`step-${i}`,`0${i+1}`,xs[i],290,100,28,18,{color:C.muted,bold:true});tx(s,`step-h-${i}`,heads[i],xs[i],395,300,42,27,{bold:true});tx(s,`step-b-${i}`,bodies[i],xs[i],470,310,105,20,{color:C.muted});}
 box(s,"fde",42,610,1196,55,C.panel,"none",false);tx(s,"fde-t","Forward Deployed Engineering：工程团队贴近现场问题，持续把反馈带回产品。",70,623,1140,30,22,{bold:true,align:"center"});
 note(s,"Palantir 官方称 Foundry 是从关键运营决策倒推构建，并将贴近客户现场的 Forward Deployed Engineering 描述为持续反馈和产品迭代的方法。",["https://www.palantir.com/platforms/foundry/","https://www.palantir.com/docs/foundry/architecture-center/overview"]);
}

// 9
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"值得学习的是方法，不是把 Palantir 当成魔法",9);
 tx(s,"strength-h","它擅长解决",42,165,500,44,29,{bold:true});tx(s,"strength-b","• 多系统、多角色、复杂业务关系\n• 数据与行动长期脱节\n• 高权限、高审计要求\n• 需要人和 AI 协同决策",42,235,520,230,24,{color:C.muted});
 tx(s,"limit-h","它不能替代",670,165,500,44,29,{bold:true});tx(s,"limit-b","• 清晰的经营目标\n• 统一、完整的数据记录\n• 部门对指标口径的共识\n• 真实工作流程和责任人",670,235,520,230,24,{color:C.muted});
 box(s,"inference",42,545,1196,88,C.amber,"none",false);tx(s,"inference-t","我们的判断：如果基础数据无法关联，先上大模型或复杂平台，只会更快地产生不可信答案。",72,568,1135,43,24,{bold:true,align:"center"});
 note(s,"左侧依据 Palantir 对复杂运营、权限和行动闭环的官方描述；右侧与底部是结合本项目作出的实施判断，不是 Palantir 官方承诺。",["https://www.palantir.com/docs/foundry/ontology/why-ontology","https://www.palantir.com/docs/foundry/object-permissioning/overview","Inference: application to the user's second-hand luxury business"]);
}

// 10 close
{
 const s=p.slides.add();s.background.fill=C.white;title(s,"对二奢项目的启示：复制策略，先做一个最小闭环",10);
 const rows=[["对象","平台、广告计划、客户、预约、回收单、商品、销售订单"],["关系","广告计划带来线索；客户形成预约；回收单生成库存商品"],["逻辑","有效线索成本、到店率、回收成交成本、销售毛利、库存周转"],["动作","调整预算、创建跟进、触发预警、确认审批、记录复盘"],["安全","老板、部门负责人、组长和员工看到与操作的范围不同"]];
 for(let i=0;i<rows.length;i++){const y=145+i*88;box(s,`map-${i}`,42,y,1196,68,i===0?C.light:i===3?C.green:C.panel,"none",false);tx(s,`map-h-${i}`,rows[i][0],70,y+17,150,34,23,{bold:true});tx(s,`map-b-${i}`,rows[i][1],250,y+17,930,34,21,{color:C.muted});}
 box(s,"final",42,615,1196,55,C.black,"none",false);tx(s,"final-t","第一阶段目标：让“哪个投放渠道真正创造利润”得到可信、可追溯、可行动的答案。",65,628,1150,30,22,{color:C.white,bold:true,align:"center"});
 note(s,"收尾回到公司项目。此页是基于 Palantir Ontology 方法作出的内部项目映射，不表示采用或采购 Palantir 产品。",["https://www.palantir.com/docs/foundry/getting-started/introductory-concepts","Inference: mapping to the user's described business process"]);
}

await fs.mkdir(TMP,{recursive:true});
for(const [i,s] of p.slides.items.entries()){const png=await p.export({slide:s,format:"png",scale:1});await fs.writeFile(`${TMP}/slide-${i+1}.png`,new Uint8Array(await png.arrayBuffer()));const lay=await s.export({format:"layout"});await fs.writeFile(`${TMP}/slide-${i+1}.layout.json`,await lay.text())}
const deck=await PresentationFile.exportPptx(p);await deck.save(OUT);console.log(OUT);
