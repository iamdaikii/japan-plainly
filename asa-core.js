// 朝の1枚 ウィジェット本体（Scriptable・ローダーから読み込まれる）
// ホーム画面に「今日のクイズ＋英語の一言」を表示。タップでその日のレッスン全文が開きます。
const DATA_URL = "https://iamdaikii.github.io/japan-plainly/asa-no-ichimai.json";
const COLORS = { jp: "#c23a22", news: "#2c5a9e", money: "#23805a", biz: "#7b4fa6", rec: "#5d6662" };

const fm = FileManager.local();
const cachePath = fm.joinPath(fm.documentsDirectory(), "asa-no-ichimai.json");

async function loadData() {
  try {
    const req = new Request(DATA_URL + "?t=" + Date.now());
    const json = await req.loadJSON();
    fm.writeString(cachePath, JSON.stringify(json));
    return json;
  } catch (e) {
    if (fm.fileExists(cachePath)) return JSON.parse(fm.readString(cachePath));
    return null;
  }
}

function todayStr() {
  const f = new DateFormatter();
  f.dateFormat = "yyyy-MM-dd";
  return f.string(new Date());
}

function pickDay(data) {
  const t = todayStr();
  const days = data.days;
  return days.find(d => d.date === t) || (t < days[0].date ? days[0] : days[days.length - 1]);
}

function nextRefresh() {
  const d = new Date();
  d.setHours(3, 0, 0, 0);
  if (d <= new Date()) d.setDate(d.getDate() + 1);
  return d;
}

function buildWidget(day) {
  const w = new ListWidget();
  w.backgroundColor = new Color(COLORS[day.catKey] || "#1d2321");
  w.setPadding(14, 16, 14, 16);
  w.refreshAfterDate = nextRefresh();

  const label = w.addText(day.rec ? "今日は1分録音の日" : "今日のクイズ ・ " + day.cat);
  label.font = Font.boldSystemFont(11);
  label.textColor = new Color("#ffffff", 0.8);
  w.addSpacer(6);

  const main = w.addText(day.rec ? day.title : day.q);
  main.font = Font.heavySystemFont(16);
  main.textColor = Color.white();
  main.minimumScaleFactor = 0.7;
  main.lineLimit = 3;
  w.addSpacer();

  const en = w.addText(day.en);
  en.font = Font.mediumSystemFont(11);
  en.textColor = new Color("#ffffff", 0.9);
  en.lineLimit = 2;
  en.minimumScaleFactor = 0.8;
  return w;
}

async function showInApp(day, data) {
  // タップするとレッスン全文（読み物・図・英語）をアプリ内で表示
  if (day.html) {
    const wv = new WebView();
    await wv.loadHTML(day.html);
    await wv.present(true);
    return;
  }
  const a = new Alert();
  a.title = day.rec ? day.title : day.q;
  a.message = day.rec ? day.steps.join("\n\n") : "答え：" + day.a + "\n\n" + day.en;
  a.addCancelAction("OK");
  await a.presentAlert();
}

module.exports.run = async function () {
const data = await loadData();
if (!data) {
  const w = new ListWidget();
  w.addText("朝の1枚：通信できるときに更新されます");
  Script.setWidget(w);
} else {
  const day = pickDay(data);
  if (config.runsInWidget) {
    Script.setWidget(buildWidget(day));
  } else {
    await showInApp(day, data);
  }
}
Script.complete();
};
