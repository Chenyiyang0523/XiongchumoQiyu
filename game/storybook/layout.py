"""Normalized composition shared by Ren'Py and the offline reader."""
def uses_layers(illustration, interactions):
    # A hotspot needs the same known object bounds in play, replay and export.
    targets=set(illustration['props']) | set(illustration['characters'].values())
    return not illustration.get('key_art') or any(i['kind']=='observe' and any(a.get('hotspot') in targets for a in i['actions']) for i in interactions)

def rectangles(illustration, manifest):
    actors = list(illustration['characters'].values())
    width = .333 if len(actors) <= 2 else .233
    characters = []
    for index, asset in enumerate(actors):
        left = (1-width)/2 if len(actors) == 1 else .033 + index*(.934-width)/max(1,len(actors)-1)
        height = .74 * manifest[asset].get('scale', 1)
        characters.append((asset,left,1-height,width,height))
    props = illustration['props']
    step = min(.16, .90/max(1,len(props)))
    start = (1-step*len(props))/2
    objects = [(asset,start+i*step,.73,step,.24) for i,asset in enumerate(props)]
    return characters, objects
