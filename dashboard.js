const $ = id => document.getElementById(id);
const SL = [["soil_moisture","Soil moisture",.05,.5,.01],["soil_N_ppm","Soil nitrogen (ppm)",5,60,1],
["clay_fraction","Clay fraction",.05,.6,.01],["slope_pct","Slope (%)",0,15,1],
["rain_24h_mm","Rain next 24 h (mm)",0,150,1],["rain_72h_mm","Rain next 72 h (mm)",0,250,1],
["days_since_fert","Days since fertilizer",0,60,1],["fert_rate_kgN_ha","Last N rate (kg/ha)",0,180,1],
["days_since_pest","Days since pesticide",0,45,1],["pest_rate_kg_ha","Pesticide rate (kg/ha)",0,3,.1],
["buffer_strip_m","Buffer strip (m)",0,20,1],["dist_to_water_m","Distance to water (m)",5,500,5]];
const PRESETS = {
  safe:  {soil_moisture:.2,soil_N_ppm:15,clay_fraction:.2,slope_pct:2,rain_24h_mm:3,rain_72h_mm:8,days_since_fert:20,fert_rate_kgN_ha:60,days_since_pest:20,pest_rate_kg_ha:.5,buffer_strip_m:15,dist_to_water_m:300},
  storm: {soil_moisture:.38,soil_N_ppm:22,clay_fraction:.45,slope_pct:9,rain_24h_mm:55,rain_72h_mm:80,days_since_fert:4,fert_rate_kgN_ha:120,days_since_pest:3,pest_rate_kg_ha:2,buffer_strip_m:2,dist_to_water_m:40}};

SL.forEach(([k,t,mn,mx,st]) => {
  $("inputs").insertAdjacentHTML("beforeend",
   `<label for="${k}">${t}<b id="v_${k}"></b></label><input type="range" id="${k}" min="${mn}" max="${mx}" step="${st}">`);
  $(k).addEventListener("input", () => { $("v_"+k).textContent = $(k).value; debounce(); });
});
function setValues(v){ SL.forEach(([k]) => { $(k).value = v[k]; $("v_"+k).textContent = v[k]; }); update(); }
document.querySelectorAll("[data-preset]").forEach(b => b.addEventListener("click", () => setValues(PRESETS[b.dataset.preset])));
$("crop").addEventListener("change", update);

const payload = () => { const o = {crop:$("crop").value}; SL.forEach(([k]) => o[k] = parseFloat($(k).value)); return o; };
const post = (url, body) => fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)}).then(r => r.json());
const col = l => "var(--" + (l==="HIGH"?"high":l==="MEDIUM"?"med":"low") + ")";
let timer; function debounce(){ clearTimeout(timer); timer = setTimeout(update, 150); }

async function update(){
  const body = payload();
  const [d, s] = await Promise.all([post("/api/predict", body), post("/api/sensitivity", body)]);
  if (d.error) return;
  const w = d.warning, rec = d.recommendation;
  [["n","nitrogen"],["p","pesticide"]].forEach(([k,n]) => {
    const e = $(k+"l"); e.textContent = w[n+"_level"] + " (" + w[n+"_risk"] + ")"; e.className = "lvl " + w[n+"_level"];
    const b = $(k+"b"); b.style.width = Math.min(100, w[n+"_risk"]*100) + "%"; b.style.background = col(w[n+"_level"]);
  });
  $("actions").innerHTML = w.actions.map(a => "<li>"+a+"</li>").join("");
  $("rec").innerHTML = [["Decision",rec.action],["This application",rec.this_application_kgN_ha+" kg N/ha"],
    ["Total N deficit",rec.total_deficit_kgN_ha+" kg N/ha"],["Delay",rec.delay_days+" days"]]
    .map(([a,b]) => `<span>${a}</span><span><b>${b}</b></span>`).join("");
  if (!s.error) drawChart(s, parseFloat($("rain_24h_mm").value));
}

function drawChart(s, current){
  const c = $("chart"), dpr = window.devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
  c.width = W*dpr; c.height = H*dpr;
  const g = c.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0,0,W,H);
  const css = getComputedStyle(document.documentElement);
  const line = css.getPropertyValue("--line").trim(), muted = css.getPropertyValue("--muted").trim();
  const cN = css.getPropertyValue("--accent").trim(), cP = css.getPropertyValue("--med").trim();
  const L=36, R=10, T=10, B=26, pw=W-L-R, ph=H-T-B;
  const X = r => L + (r/150)*pw, Y = v => T + (1-Math.min(1,v))*ph;
  g.font = "11px system-ui"; g.fillStyle = muted; g.strokeStyle = line; g.lineWidth = 1;
  [0,.25,.5,.75,1].forEach(v => { g.beginPath(); g.moveTo(L,Y(v)); g.lineTo(W-R,Y(v)); g.stroke(); g.fillText(v.toFixed(2), 2, Y(v)+4); });
  [0,50,100,150].forEach(r => g.fillText(r+" mm", X(r)-12, H-8));
  [[s.nitrogen,cN],[s.pesticide,cP]].forEach(([arr,color]) => {
    g.strokeStyle = color; g.lineWidth = 2.5; g.beginPath();
    arr.forEach((v,i) => i ? g.lineTo(X(s.rain[i]),Y(v)) : g.moveTo(X(s.rain[i]),Y(v))); g.stroke();
  });
  g.strokeStyle = muted; g.setLineDash([4,4]); g.lineWidth = 1; g.beginPath();
  g.moveTo(X(current),T); g.lineTo(X(current),T+ph); g.stroke(); g.setLineDash([]);
  g.fillStyle = muted; g.fillText("now", Math.min(X(current)+4, W-34), T+10);
}

$("send").addEventListener("click", async () => {
  const d = await post("/api/alert", {...payload(), phone:$("phone").value, whatsapp:$("wa").checked});
  $("alertmsg").textContent = d.error || d.message;
});
window.addEventListener("resize", debounce);
setValues(PRESETS.storm);
