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
  const ds = days.filter(d => !d.req);
  return ds.find(d => d.date === t) || (t < ds[0].date ? ds[0] : ds[ds.length - 1]);
}

// 復習：1・3・7・14・30・60日前の問題から1つ（忘れたころに出す）
function addDays(str, n) {
  const d = new Date(str + "T12:00:00");
  d.setDate(d.getDate() + n);
  const f = new DateFormatter(); f.dateFormat = "yyyy-MM-dd";
  return f.string(d);
}
function pickReview(data) {
  const t = todayStr();
  const past = data.days.filter(d => d.q && d.date < t);
  if (!past.length) return null;
  for (const o of [1, 3, 7, 14, 30, 60]) {
    const hit = past.find(d => d.date === addDays(t, -o));
    if (hit && o > 1) return Object.assign({ ago: o }, hit);
  }
  const hit1 = past.find(d => d.date === addDays(t, -1));
  if (hit1) return Object.assign({ ago: 1 }, hit1);
  const n = Math.floor(Date.parse(t) / 86400000);
  const r = past[n % past.length];
  return Object.assign({ ago: null }, r);
}
function reviewMode() { return new Date().getHours() >= 12; }

function nextRefresh() {
  const d = new Date();
  const now = new Date();
  d.setHours(3, 0, 0, 0);
  if (d > now) return d;
  d.setHours(12, 0, 0, 0);
  if (d > now) return d;
  d.setDate(d.getDate() + 1); d.setHours(3, 0, 0, 0);
  return d;
}

function buildWidget(day, isReview) {
  const w = new ListWidget();
  w.backgroundColor = new Color(COLORS[day.catKey] || "#1d2321");
  w.setPadding(14, 16, 14, 16);
  w.refreshAfterDate = nextRefresh();

  const label = w.addText(isReview ? "復習 ・ " + (day.ago ? day.ago + "日前" : "前") + "の問題" : day.rec ? "今日は英文テストの日" : "今日のクイズ ・ " + day.cat);
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

async function showInApp(day, data, isReview, today) {
  if (isReview) {
    const a = new Alert();
    a.title = day.q;
    a.message = "答え：" + day.a + "\n\n" + day.en;
    a.addAction("この回のレッスンを読み直す");
    a.addAction("今日のレッスンを開く");
    a.addCancelAction("OK");
    const r = await a.presentAlert();
    if (r === 0) return showInApp(day, data, false);
    if (r === 1) return showInApp(today, data, false);
    return;
  }
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
  const today = pickDay(data);
  const rev = pickReview(data);
  const useReview = rev && (reviewMode() || today.rec);
  const day = useReview ? rev : today;
  if (config.runsInWidget) {
    Script.setWidget(buildWidget(day, useReview));
  } else {
    await showInApp(day, data, useReview, today);
  }
}
Script.complete();
};
