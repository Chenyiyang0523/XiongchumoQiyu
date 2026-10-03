"""Self-contained offline HTML book; all text escaped, assets and font embedded."""
import base64
import html
import json
from pathlib import Path
from .layout import rectangles, uses_layers

def export_html(story, destination, read_asset):
    assets = {}
    paths = {a: spec['path'] for a, spec in story['manifest'].items()}
    used = set()
    for page in story['pages']:
        art = page['illustration']
        used.add(art['scene'])
        used.update(art['characters'].values())
        used.update(art['props'])
        if art.get('key_art'):
            used.add(art['key_art'])
    for aid in used:
        path = paths[aid]
        mime = 'image/webp' if path.endswith('.webp') else 'image/png'
        assets[aid] = 'data:' + mime + ';base64,' + base64.b64encode(read_asset(path)).decode()
    font = base64.b64encode(read_asset('SourceHanSansLite.ttf')).decode()
    layouts = {p['id']: rectangles(p['illustration'], story['manifest']) for p in story['pages']}
    layered = {p['id']: uses_layers(p['illustration'], p['interactions']) for p in story['pages']}
    data = json.dumps({'book': story, 'assets': assets, 'layouts': layouts, 'layered':layered}, ensure_ascii=False).replace('<', '\\u003c')
    title = html.escape(story['blueprint']['title'])
    doc = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + title + r'''</title><style>
@font-face{font-family:book;src:url(data:font/ttf;base64,''' + font + r''')}*{box-sizing:border-box}body{font-family:book,sans-serif;background:#f4eedf;color:#213d31;margin:0}main{max-width:1100px;margin:auto;padding:24px}h1{font-size:28px}#art{position:relative;aspect-ratio:16/9;overflow:hidden;border-radius:22px;background:#cad8b5}#art img.bg{width:100%;height:100%;object-fit:cover}#art img.actor{position:absolute;height:76%;width:32%;bottom:0;object-fit:contain}#art img.prop{position:absolute;height:19%;width:17%;bottom:3%;object-fit:contain}article{padding:24px;background:#fffdf7;border-radius:20px;margin-top:16px;font-size:22px;line-height:1.9}button{font:inherit;padding:12px 24px;border:0;border-radius:30px;background:#234e3a;color:white;cursor:pointer;margin:8px}button:disabled{opacity:.4}nav{display:flex;align-items:center;justify-content:center}#detail{font-size:16px;white-space:pre-wrap;color:#526858}#mock{color:#98612c}</style>
<main><h1>''' + title + r'''</h1><p id="goal"></p><p id="mock"></p><div id="art"></div><article><h2 id="title"></h2><div id="text"></div><p id="detail"></p></article><nav><button id="prev">上一页</button><span id="number"></span><button id="next">下一页</button></nav></main>
<script type="application/json" id="bookdata">''' + data + r'''</script><script>
const d=JSON.parse(document.getElementById('bookdata').textContent),b=d.book;let n=0;
document.getElementById('goal').textContent='故事目标：'+b.blueprint.goal;
document.getElementById('mock').textContent=b.mock?'开发模拟绘本 · 不代表真实模型验收':'';
function draw(){const p=b.pages[n],a=p.illustration,art=document.getElementById('art');art.replaceChildren();
function img(id,cls,rect){let x=document.createElement('img');x.src=d.assets[id];x.className=cls;if(rect){x.style.left=rect[0]*100+'%';x.style.top=rect[1]*100+'%';x.style.width=rect[2]*100+'%';x.style.height=rect[3]*100+'%';x.style.bottom='auto'}art.append(x)}
img(d.layered[p.id]?a.scene:a.key_art,'bg');if(d.layered[p.id]){d.layouts[p.id][0].forEach(r=>img(r[0],'actor',r.slice(1)));d.layouts[p.id][1].forEach(r=>img(r[0],'prop',r.slice(1)))}
document.getElementById('title').textContent=p.title;document.getElementById('text').textContent=p.text;
let selected=new Set(p.choices.map(c=>c.action_id));let labels=p.interactions.flatMap(i=>i.actions).filter(a=>selected.has(a.id)).map(a=>a.label);labels.push(...p.choices.filter(c=>c.label).map(c=>c.label));
document.getElementById('detail').textContent=(labels.length?'我的行动：'+labels.join('；'):'')+(p.discussion?'\n我们的理由：'+p.discussion:'')+(n===b.pages.length-1&&b.ending?'\n结局：'+b.ending.title+'\n'+b.ending.text:'');
document.getElementById('number').textContent=(n+1)+' / '+b.pages.length;document.getElementById('prev').disabled=n===0;document.getElementById('next').disabled=n===b.pages.length-1}
document.getElementById('prev').onclick=()=>{n--;draw()};document.getElementById('next').onclick=()=>{n++;draw()};document.onkeydown=e=>{if(e.key==='ArrowLeft'&&n>0){n--;draw()}if(e.key==='ArrowRight'&&n<b.pages.length-1){n++;draw()}};draw();
</script></html>'''
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Path(destination).write_text(doc, encoding='utf-8')
    return str(destination)
