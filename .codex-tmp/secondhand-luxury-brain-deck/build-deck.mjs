import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "/Users/szzx/szzx/二奢智慧经营大脑-项目启动宣讲.pptx";
const IMG = "/var/folders/0m/8mjzmcts6j31szf5h53x0b300000gn/T/codex-clipboard-97364d33-324e-4ce1-beee-cc15174829fc.png";
const TMP = "/Users/szzx/szzx/.codex-tmp/secondhand-luxury-brain-deck/rendered";

const C = { ink: "#111111", muted: "#667085", panel: "#F2F4F7", rule: "#D0D5DD", blue: "#3D8DFF", light: "#D9F0FF", green: "#DDF5E5", pink: "#FCE7EA", amber: "#FFF0C7", white: "#FFFFFF" };
const FONT = "PingFang SC";

const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function box(slide, name, x, y, w, h, fill = "none", line = "none", radius = false) {
  return slide.shapes.add({ geometry: radius ? "roundRect" : "rect", name, position: { left:x, top:y, width:w, height:h }, fill, line: { style:"solid", fill:line, width: line === "none" ? 0 : 1 } });
}
function tx(slide, name, text, x, y, w, h, size=22, opts={}) {
  const s = slide.shapes.add({ geometry:"textbox", name, position:{left:x,top:y,width:w,height:h}, fill:"none", line:{style:"solid",fill:"none",width:0} });
  s.text = text;
  s.text.style = { fontSize:size, typeface:FONT, color:opts.color || C.ink, bold:!!opts.bold, alignment:opts.align || "left", verticalAlignment:opts.valign || "top", autoFit:opts.autoFit || "shrinkText" };
  return s;
}
function title(slide, text, n) {
  tx(slide, `title-${n}`, text, 42, 34, 1160, 70, 38, {bold:true});
  tx(slide, `page-${n}`, String(n).padStart(2,"0"), 1180, 665, 55, 24, 14, {color:C.muted,align:"right"});
}
function note(slide, body, source="用户提供的业务描述与流程图") {
  slide.speakerNotes.textFrame.setText(`${body}\n\n[Sources]\n- ${source}\n[/Sources]`);
}
function rule(slide, x1, y, x2, color=C.rule, width=1) {
  slide.shapes.add({ geometry:"straightConnector1", position:{left:x1,top:y,width:x2-x1,height:0}, fill:"none", line:{style:"solid",fill:color,width} });
}

// 1 — sparse cover, based on Codex Grid cover hierarchy
{
  const s=p.slides.add(); s.background.fill=C.white;
  tx(s,"eyebrow","项目启动宣讲｜内部讨论稿",42,38,420,32,17,{color:C.muted,bold:true});
  tx(s,"cover-title","二奢智慧\n经营大脑",42,170,760,210,64,{bold:true});
  tx(s,"cover-subtitle","让投放、回收、库存与销售的数据连起来，\n让每一次经营判断都有事实依据。",42,450,770,105,27,{color:C.muted});
  box(s,"cover-accent",1040,40,198,590,C.light,"none",false);
  tx(s,"cover-keywords","数据\n关系\n决策\n记忆",1080,155,120,300,34,{bold:true,align:"center",valign:"middle"});
  note(s,"开场先统一目标：我们不是做一个炫技工具，而是让经营问题更快得到可信答案。第一阶段从投放到回收的闭环开始。");
}

// 2
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"业务已经形成闭环，但数据还没有形成闭环",2);
  tx(s,"left-big","信息分散",42,165,400,70,38,{bold:true});
  tx(s,"left-body","投放平台、客户跟进、门店回收、库存和销售各自记录。\n\n同一个客户、商品或订单，很难沿着整条链路追踪。",42,250,500,250,24,{color:C.muted});
  rule(s,620,145,620,C.rule,2);
  tx(s,"right-big","判断靠经验",680,165,400,70,38,{bold:true});
  tx(s,"right-body","老板问“抖音和百度哪个更好”，不同人可能给出不同答案。\n\n真正需要比较的，不只是线索成本，而是最终回收成交与销售毛利。",680,250,500,250,24,{color:C.muted});
  box(s,"bottom-callout",42,565,1196,72,C.ink,"none",false);
  tx(s,"bottom-callout-text","要解决的核心：同一套事实、同一套口径、同一条业务链。",70,582,1140,40,26,{color:C.white,bold:true,align:"center"});
  note(s,"这页避免把问题归因于某个部门。强调目前是系统和口径分散，而不是谁做得不好。智慧大脑首先解决共同事实的问题。");
}

// 3
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"智慧大脑不是聊天机器人，而是“数据 + 业务关系 + 行动”",3);
  const xs=[42,453,864], fills=[C.light,C.panel,C.green];
  const nums=["01","02","03"], heads=["看见事实","理解关系","推动行动"];
  const bodies=["连接投放、线索、预约、到店、回收、库存、销售。","知道平台、客户、员工、商品和订单之间如何关联。","发现异常、解释原因、给出建议，并跟踪执行结果。"];
  for(let i=0;i<3;i++){
    box(s,`layer-${i}`,xs[i],210,375,330,fills[i],"none",false);
    tx(s,`num-${i}`,nums[i],xs[i]+28,235,90,42,22,{color:C.muted,bold:true});
    tx(s,`head-${i}`,heads[i],xs[i]+28,305,315,55,32,{bold:true});
    tx(s,`body-${i}`,bodies[i],xs[i]+28,390,315,105,21,{color:C.muted});
  }
  note(s,"用三层结构解释产品。模型只负责理解问题和组织答案，经营数字必须由数据库与明确指标计算。");
}

// 4 user image evidence
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"现有流程图已经是第一版业务地图",4);
  const bytes = await fs.readFile(IMG);
  s.images.add({ blob:bytes, contentType:"image/png", alt:"公司从线上获客、线下回收到销售阶段的业务流程图", fit:"contain", position:{left:42,top:130,width:820,height:500} });
  box(s,"insight-panel",900,130,338,500,C.panel,"none",false);
  tx(s,"insight-head","接下来要补的\n不是更多流程框",930,170,278,100,29,{bold:true});
  tx(s,"insight-body","而是每个节点对应：\n\n• 哪张数据表\n• 谁负责录入\n• 用什么唯一编号关联\n• 指标如何计算\n• 发生异常后谁行动",930,315,270,245,21,{color:C.muted});
  note(s,"请参与成员共同校对这张图。流程图是业务共识的起点，后续要把每个节点映射到系统字段、责任人和指标口径。","用户提供的公司业务流程图：codex-clipboard-97364d33-324e-4ce1-beee-cc15174829fc.png");
}

// 5 ontology map
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"第一版业务本体：把关键对象和关系统一起来",5);
  const nodes=[
    ["平台 / 广告计划",60,205,C.light],["线索 / 客户",305,205,C.panel],["预约 / 到店",550,205,C.amber],
    ["鉴定 / 回收单",795,205,C.green],["库存商品",915,430,C.panel],["销售订单 / 毛利",670,430,C.pink]
  ];
  // connectors first
  const edges=[[250,250,305,250],[495,250,550,250],[740,250,795,250],[900,310,980,430],[860,485,915,485]];
  for (const [x1,y1,x2,y2] of edges) s.shapes.add({geometry:"straightConnector1",position:{left:x1,top:y1,width:x2-x1,height:y2-y1},fill:"none",line:{style:"solid",fill:C.ink,width:2,endArrowType:"triangle"}});
  for (const [label,x,y,fill] of nodes){ box(s,`node-${label}`,x,y,190,105,fill,C.rule,true); tx(s,`node-text-${label}`,label,x+15,y+22,160,60,22,{bold:true,align:"center",valign:"middle"}); }
  tx(s,"relation-note","组织关系贯穿全链：部门 → 小组 → 员工 → 责任对象",60,585,1120,42,24,{color:C.muted,align:"center"});
  note(s,"所谓本体，不需要向大家讲复杂定义。可以把它理解成：公司里有哪些关键对象、它们有什么关系、允许做什么动作。第一版只覆盖核心闭环。");
}

// 6 MVP funnel
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"第一个试点：先回答投放到底有没有带来利润",6);
  const labels=["投放金额","有效线索","预约到店","回收成交","商品售出","最终毛利"];
  const widths=[1130,980,830,680,530,380];
  const fills=["#E9F5FF","#D8EDFF","#C6E4FF","#B5DCFF","#8CC7FF",C.blue];
  for(let i=0;i<labels.length;i++){
    const x=(1280-widths[i])/2, y=145+i*78;
    box(s,`funnel-${i}`,x,y,widths[i],58,fills[i],"none",false);
    tx(s,`funnel-text-${i}`,labels[i],x,y+12,widths[i],35,22,{bold:true,align:"center",color:i===5?C.white:C.ink});
  }
  tx(s,"mvp-foot","不只比较“线索便不便宜”，而是比较“最终为公司创造了什么”。",150,635,980,35,24,{bold:true,align:"center"});
  note(s,"这一页是项目价值的核心。第一阶段优先打通投放计划到回收成交；销售毛利如果暂时无法完整关联，可以作为第二阶段，但数据结构从一开始就预留。");
}

// 7 example Q&A
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"未来的经营提问，应该得到可追溯的答案",7);
  tx(s,"question-label","老板问",42,150,180,32,18,{color:C.muted,bold:true});
  tx(s,"question","“最近30天，抖音和百度哪个投放效果更好？”",42,195,1120,65,33,{bold:true});
  box(s,"answer",42,310,1196,255,C.panel,"none",false);
  tx(s,"answer-head","系统回答（示例结构，不代表真实数据）",70,338,520,34,19,{color:C.muted,bold:true});
  tx(s,"answer-body","结论：百度线索成本更高，但回收成交成本更低。\n依据：投放金额 → 有效线索 → 到店 → 回收成交，逐层展示。\n原因：百度有效率与到店率更高；抖音在线索到预约环节流失较大。\n建议：小幅调整预算，并连续观察两周。",70,395,1090,135,23,{});
  tx(s,"trace","每个数字都可点击回到原始记录；每个建议都标明使用的口径。",150,610,980,35,22,{color:C.blue,bold:true,align:"center"});
  note(s,"强调可信性：回答必须包含结论、数据依据、指标口径、原因与建议。示例不使用虚构数值，避免参与成员误以为已经完成分析。");
}

// 8 memory
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"“记忆”分三层：公司规则、实时数据、历史决策",8);
  const ys=[160,320,480], fills=[C.light,C.panel,C.green], heads=["企业长期记忆","业务实时记忆","决策与对话记忆"], bodies=["组织架构、部门职责、业务流程、指标口径、公司制度","投放、客户、预约、回收、库存、订单等实时状态","老板关注重点、已经形成的判断规则、会议决定与后续动作"];
  for(let i=0;i<3;i++){
    box(s,`memory-${i}`,42,ys[i],1196,112,fills[i],"none",false);
    tx(s,`memory-head-${i}`,heads[i],75,ys[i]+25,290,55,27,{bold:true});
    tx(s,`memory-body-${i}`,bodies[i],390,ys[i]+29,790,55,22,{color:C.muted});
  }
  note(s,"说明记忆不是把所有聊天永久保存。重要规则要经过确认后进入企业记忆；实时业务信息仍以数据库为准；敏感信息必须受权限控制。");
}

// 9 participation
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"三个部门共同定义大脑，而不是把项目交给某一个部门",9);
  const xs=[42,453,864], colors=[C.light,C.amber,C.green];
  const heads=["网络部","门店 / 运营中心","综合部"];
  const bodies=["提供平台、账户、计划与线索字段\n统一有效线索与投放归因口径\n确认常用分析问题","确认预约、到店、鉴定、议价、成交节点\n统一回收成交与员工归属\n补齐关键状态记录","确认库存、销售、退款和毛利口径\n建立商品唯一编号\n反馈库龄与销售异常规则"];
  for(let i=0;i<3;i++){
    box(s,`dept-${i}`,xs[i],175,375,395,colors[i],"none",false);
    tx(s,`dept-head-${i}`,heads[i],xs[i]+30,210,315,45,30,{bold:true});
    tx(s,`dept-body-${i}`,bodies[i],xs[i]+30,300,315,200,21,{color:C.muted});
  }
  tx(s,"common","共同原则：先保证真实、完整、可关联，再追求“智能”。",100,620,1080,38,25,{bold:true,align:"center"});
  note(s,"各部门不是单纯提供数据，而是共同定义业务语义。现场可以让每个部门确认一位业务负责人和一位数据联系人。");
}

// 10 roadmap / close
{
  const s=p.slides.add(); s.background.fill=C.white; title(s,"先用一个最小闭环证明价值，再逐步扩展",10);
  rule(s,95,360,1185,C.ink,2);
  const xs=[95,450,815], labels=["第 1–2 周","第 3–6 周","第 7–8 周"], heads=["盘点与统一","投放分析 MVP","试运行与复盘"], bodies=["系统与数据表清单\n指标口径与唯一编号\n确定首批问题","打通投放—线索—到店—回收\n搭建经营总览与问答\n建立权限与记忆规则","邀请真实用户使用\n核对答案准确性\n形成下一阶段清单"];
  for(let i=0;i<3;i++){
    box(s,`dot-${i}`,xs[i],351,18,18,C.blue,"none",true);
    tx(s,`time-${i}`,labels[i],xs[i],300,250,32,19,{color:C.muted,bold:true});
    tx(s,`road-head-${i}`,heads[i],xs[i],405,300,42,26,{bold:true});
    tx(s,`road-body-${i}`,bodies[i],xs[i],470,300,120,20,{color:C.muted});
  }
  box(s,"decision",42,620,1196,54,C.ink,"none",false);
  tx(s,"decision-text","本次启动会要确定：项目负责人、三部门接口人、首批数据源、首批 10 个经营问题。",58,633,1160,30,22,{color:C.white,bold:true,align:"center"});
  note(s,"收尾不说谢谢，而是明确启动会要做出的决定。时间为建议节奏，可以根据系统复杂度调整；最重要的是先锁定首批数据和经营问题。");
}

await fs.mkdir(TMP,{recursive:true});
for (const [i,slide] of p.slides.items.entries()) {
  const png=await p.export({slide,format:"png",scale:1});
  await fs.writeFile(`${TMP}/slide-${i+1}.png`,new Uint8Array(await png.arrayBuffer()));
  const layout=await slide.export({format:"layout"});
  await fs.writeFile(`${TMP}/slide-${i+1}.layout.json`,await layout.text());
}
const montage=await p.export({format:"webp",montage:true,scale:1});
await fs.writeFile(`${TMP}/montage.webp`,new Uint8Array(await montage.arrayBuffer()));
const deck=await PresentationFile.exportPptx(p);
await deck.save(OUT);
console.log(OUT);
