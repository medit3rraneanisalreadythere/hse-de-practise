const state = { result: null };
const $ = (id) => document.getElementById(id);

const elements = {
  form: $("generatorForm"), prompt: $("prompt"), charCount: $("charCount"), examples: $("examples"),
  source: $("source"), destination: $("destination"), sourceConnection: $("sourceConnection"),
  destinationConnection: $("destinationConnection"), schedule: $("schedule"), owner: $("owner"),
  policy: $("policy"), quality: $("quality"), notifications: $("notifications"),
  generateButton: $("generateButton"), formError: $("formError"), empty: $("emptyState"),
  loading: $("loadingState"), result: $("resultContent"), loadingText: $("loadingText"),
};

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}

async function initialize() {
  try {
    const [health, examples] = await Promise.all([api("/api/health"), api("/api/examples")]);
    $("modeText").textContent = providerLabel(health.mode, health.model);
    $("versionText").textContent = `DAG Forge v${health.version}`;
    elements.examples.innerHTML = "";
    examples.forEach((example) => {
      const button = document.createElement("button");
      button.type = "button"; button.textContent = example.title;
      button.addEventListener("click", () => applyExample(example));
      elements.examples.append(button);
    });
  } catch (error) {
    $("modeText").textContent = "API недоступен";
    elements.examples.innerHTML = "";
  }
}

function applyExample(example) {
  elements.prompt.value = example.prompt;
  elements.source.value = example.source;
  elements.destination.value = example.destination;
  elements.schedule.value = example.schedule;
  updateCount();
  elements.prompt.focus();
}

function updateCount() { elements.charCount.textContent = elements.prompt.value.length; }

function payloadFromForm() {
  return {
    prompt: elements.prompt.value,
    source: elements.source.value,
    destination: elements.destination.value,
    schedule: elements.schedule.value,
    source_connection_id: elements.sourceConnection.value,
    destination_connection_id: elements.destinationConnection.value,
    owner: elements.owner.value,
    policy_pack: elements.policy.value,
    include_quality_checks: elements.quality.checked,
    include_notifications: elements.notifications.checked,
  };
}

const loadingMessages = ["Строим типизированный план…", "Проверяем зависимости и циклы…", "Рендерим безопасный Python…", "Запускаем policy checks…"];

async function generate(event) {
  event.preventDefault(); elements.formError.textContent = "";
  if (!elements.form.reportValidity()) return;
  elements.empty.classList.add("hidden"); elements.result.classList.add("hidden"); elements.loading.classList.remove("hidden");
  elements.generateButton.disabled = true;
  let index = 0; const timer = setInterval(() => { index = (index + 1) % loadingMessages.length; elements.loadingText.textContent = loadingMessages[index]; }, 900);
  try {
    state.result = await api("/api/generate", { method: "POST", body: JSON.stringify(payloadFromForm()) });
    renderResult(state.result);
    elements.loading.classList.add("hidden"); elements.result.classList.remove("hidden");
    if (window.innerWidth < 1180) $("result").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    elements.loading.classList.add("hidden"); elements.empty.classList.remove("hidden");
    elements.formError.textContent = `Не удалось сгенерировать DAG: ${error.message}`;
  } finally { clearInterval(timer); elements.generateButton.disabled = false; }
}

function renderResult(result) {
  const spec = result.spec; const report = result.validation;
  $("resultMode").textContent = providerLabel(result.mode, result.model).toUpperCase();
  $("dagTitle").textContent = spec.dag_id; $("dagDescription").textContent = spec.description;
  $("scoreValue").textContent = report.score; $("scoreRing").style.background = `conic-gradient(var(--lime) ${report.score}%, #2d333d 0)`;
  $("resultMeta").innerHTML = `<span>SCHEDULE <b>${escapeHtml(spec.schedule)}</b></span><span>TASKS <b>${spec.tasks.length}</b></span><span>EDGES <b>${spec.tasks.reduce((n,t)=>n+t.upstream_ids.length,0)}</b></span><span>OWNER <b>${escapeHtml(spec.owner)}</b></span>`;
  $("fileName").textContent = `${spec.dag_id}.py`; $("codeOutput").textContent = result.code; $("specOutput").textContent = JSON.stringify(spec, null, 2);
  $("findingCount").textContent = report.findings.length; renderGraph(spec); renderValidation(report);
  $("generationNotes").innerHTML = result.generation_notes.map(note => `<span>• ${escapeHtml(note)}</span>`).join("");
}

function renderGraph(spec) {
  const tasks = spec.tasks; const levels = {};
  function level(id) { if (levels[id] !== undefined) return levels[id]; const task = tasks.find(t=>t.task_id===id); return levels[id] = task.upstream_ids.length ? Math.max(...task.upstream_ids.map(level)) + 1 : 0; }
  tasks.forEach(t => level(t.task_id));
  const columns = Math.max(...Object.values(levels)) + 1; const grouped = Array.from({length:columns},()=>[]); tasks.forEach(t=>grouped[levels[t.task_id]].push(t));
  const boxW=142, boxH=60, gapX=58, gapY=28, margin=28; const maxRows=Math.max(...grouped.map(g=>g.length)); const width=margin*2+columns*boxW+(columns-1)*gapX; const height=margin*2+maxRows*boxH+(maxRows-1)*gapY;
  const positions={}; grouped.forEach((group,x)=>{ const groupHeight=group.length*boxH+(group.length-1)*gapY; const start=(height-groupHeight)/2; group.forEach((task,y)=>positions[task.task_id]={x:margin+x*(boxW+gapX),y:start+y*(boxH+gapY)}); });
  const esc = escapeHtml; let edges=""; tasks.forEach(task=>task.upstream_ids.forEach(parent=>{const a=positions[parent],b=positions[task.task_id],x1=a.x+boxW,y1=a.y+boxH/2,x2=b.x,y2=b.y+boxH/2,m=(x1+x2)/2;edges+=`<path class="graph-edge" marker-end="url(#arrow)" d="M${x1} ${y1} C${m} ${y1},${m} ${y2},${x2} ${y2}"/>`; }));
  let nodes=""; tasks.forEach((task,i)=>{const p=positions[task.task_id];nodes+=`<g transform="translate(${p.x} ${p.y})"><rect class="graph-box ${task.kind}" rx="8" width="${boxW}" height="${boxH}"/><circle class="graph-dot" cx="13" cy="14" r="2.5"/><text class="graph-index" x="123" y="17">${String(i+1).padStart(2,"0")}</text><text class="graph-title" x="13" y="35">${esc(crop(task.title,20))}</text><text class="graph-kind" x="13" y="49">${esc(task.kind.toUpperCase())}</text></g>`;});
  $("dagGraph").innerHTML=`<svg viewBox="0 0 ${width} ${height}" width="${Math.max(width,500)}" aria-label="Граф DAG"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#596473"/></marker></defs>${edges}${nodes}</svg>`;
}

function renderValidation(report) {
  const container=$("validationOutput");
  if (!report.findings.length) { container.innerHTML=`<div class="all-clear"><strong>✓</strong><h3>Все ${report.checks_run} проверок пройдены</h3><p>Синтаксис, Airflow policy, секреты и опасные вызовы проверены.</p></div>`; return; }
  container.innerHTML=report.findings.map(f=>`<article class="finding ${f.severity}"><span class="finding-icon">${f.severity==='error'?'!':f.severity==='warning'?'△':'i'}</span><div><h4>${escapeHtml(f.title)}</h4><p>${escapeHtml(f.message)}</p></div><code>${escapeHtml(f.rule_id)}${f.line?` · L${f.line}`:''}</code></article>`).join("");
}

function switchTab(event) { const button=event.target.closest("button[data-tab]"); if(!button)return; document.querySelectorAll(".tabs button").forEach(b=>b.classList.toggle("active",b===button)); document.querySelectorAll(".tab-panel").forEach(p=>p.classList.toggle("active",p.id===`tab-${button.dataset.tab}`)); }
function downloadCode(){if(!state.result)return;const blob=new Blob([state.result.code],{type:"text/x-python;charset=utf-8"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`${state.result.spec.dag_id}.py`;a.click();URL.revokeObjectURL(a.href);}
async function copyCode(){if(!state.result)return;await navigator.clipboard.writeText(state.result.code);const b=$("copyButton");b.textContent="Скопировано ✓";setTimeout(()=>b.textContent="Копировать",1400);}
async function publishToAirflow(){
  if(!state.result)return;
  const button=$("publishButton"); const airflowWindow=window.open("about:blank","_blank");
  button.disabled=true; button.textContent="Публикуем…";
  try {
    const published=await api("/api/airflow/publish",{method:"POST",body:JSON.stringify({spec:state.result.spec})});
    button.textContent="Опубликовано ✓";
    if(airflowWindow) airflowWindow.location.href=published.airflow_url;
    else window.location.href=published.airflow_url;
  } catch(error) {
    if(airflowWindow) airflowWindow.close();
    button.textContent="Повторить публикацию";
    elements.formError.textContent=`Не удалось опубликовать DAG: ${error.message}`;
  } finally { button.disabled=false; }
}
function escapeHtml(value){return String(value).replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));}
function crop(text,max){return text.length>max?`${text.slice(0,max-1)}…`:text;}
function providerLabel(mode,model){if(mode==="ollama")return `Local AI · ${model}`;if(mode==="openai"||mode==="ai")return `OpenAI · ${model}`;return "Demo mode · ready";}

elements.prompt.addEventListener("input",updateCount); elements.form.addEventListener("submit",generate); document.querySelector(".tabs").addEventListener("click",switchTab);
$("downloadButton").addEventListener("click",downloadCode); $("copyButton").addEventListener("click",copyCode); $("publishButton").addEventListener("click",publishToAirflow); $("themeButton").addEventListener("click",()=>document.body.classList.toggle("light"));
initialize();
