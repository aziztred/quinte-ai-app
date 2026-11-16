import re
import threading
import requests
from datetime import datetime, timedelta
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window

Window.clearcolor = (0.07, 0.09, 0.15, 1)

ELITE_NUMBER_ONE = ("RAFFIN", "BAZIRE", "SOUMILLON", "GUYON", "BARZALONA")
STRONG_DRIVERS = ("ABRIVARD", "GELORMINI", "LEBOURGEOIS", "NIVARD", "THOMAIN", "PLOQUIN", "ROCHARD", "LOCQUENEUX", "PASQUIER", "DEMURO", "LEMAIRE")

def analyze_musique(m_str):
    if not m_str or not isinstance(m_str, str):
        return 0, 0.0
    results = re.findall(r'(\d+|D|A|T)[a-zA-Z]', m_str)[:6]
    recent_dq = sum(1 for r in results[:4] if r in ('D', 'A', 'T'))
    form_pts = 0.0
    weights = (1.6, 1.3, 1.0, 0.8, 0.6, 0.4)
    for i, r in enumerate(results):
        w = weights[i]
        if r == '1': form_pts += 12 * w
        elif r in ('2', '3'): form_pts += 7 * w
        elif r in ('4', '5'): form_pts += 4 * w
        elif r in ('D', 'A', 'T'): form_pts -= 5 * w
    return recent_dq, max(0.0, form_pts)

class QuinteAndroidApp(App):
    def build(self):
        self.title = "Quinte AI Pro"
        root = BoxLayout(orientation="vertical", padding=15, spacing=10)

        title_lbl = Label(
            text="Quinte AI Pro - Quinte+ Predictor",
            font_size="20sp", bold=True, color=(0.98, 0.75, 0.14, 1),
            size_hint_y=None, height=50
        )
        root.add_widget(title_lbl)

        btn_box = BoxLayout(orientation="horizontal", spacing=10, size_hint_y=None, height=60)
        btn_today = Button(text="Today Quinte (1)", background_color=(0.06, 0.72, 0.5, 1), bold=True, font_size="16sp")
        btn_today.bind(on_press=lambda x: self.start_fetch(0))

        btn_tomorrow = Button(text="Tomorrow Quinte (2)", background_color=(0.23, 0.51, 0.96, 1), bold=True, font_size="16sp")
        btn_tomorrow.bind(on_press=lambda x: self.start_fetch(1))

        btn_box.add_widget(btn_today)
        btn_box.add_widget(btn_tomorrow)
        root.add_widget(btn_box)

        self.status_lbl = Label(text="Press a button to get predictions", font_size="14sp", color=(0.22, 0.74, 0.97, 1), size_hint_y=None, height=40)
        root.add_widget(self.status_lbl)

        self.combo_lbl = Label(text="", font_size="18sp", bold=True, color=(0.98, 0.75, 0.14, 1), size_hint_y=None, height=45)
        root.add_widget(self.combo_lbl)

        scroll = ScrollView()
        self.list_layout = BoxLayout(orientation="vertical", spacing=8, size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

        return root

    def start_fetch(self, offset):
        self.status_lbl.text = "Fetching PMU data..."
        self.combo_lbl.text = ""
        self.list_layout.clear_widgets()
        threading.Thread(target=self.fetch_data, args=(offset,), daemon=True).start()

    def fetch_data(self, offset):
        target_date = datetime.now() + timedelta(days=offset)
        date_str = target_date.strftime("%d%m%Y")
        display_date = target_date.strftime("%Y-%m-%d")
        host = "online.turfinfo.api.pmu.fr"
        path_api = "/rest/client/61/programme/"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

        try:
            res = requests.get(f"https://{host}{path_api}{date_str}", headers=headers, timeout=15)
            if res.status_code != 200:
                Clock.schedule_once(lambda dt: self.show_error("Connection error with PMU"))
                return

            reunions = res.json().get("programme", {}).get("reunions", [])
            q_info = None
            for r in reunions:
                for c in r.get("courses", []):
                    if "QUINTE" in str(c.get("paris", "")).upper():
                        q_info = {
                            'r': r.get('numOfficiel'), 'c': c.get('numOrdre'),
                            'hippo': r.get('hippodrome', {}).get('libelleCourt', ''),
                            'dist': int(c.get('distance', 2100)),
                            'disc': str(c.get('discipline', 'TROT')).upper(),
                            'cond': str(c.get('conditions', '')).upper()
                        }
                        break
                if q_info: break

            if not q_info:
                Clock.schedule_once(lambda dt: self.show_error(f"Quinte for {display_date} not published yet"))
                return

            p_res = requests.get(f"https://{host}{path_api}{date_str}/R{q_info['r']}/C{q_info['c']}/participants", headers=headers, timeout=15)
            participants = p_res.json().get("participants", [])
            if not participants:
                Clock.schedule_once(lambda dt: self.show_error("Participants list empty"))
                return

            is_trot = any(k in q_info['disc'] for k in ("TROT", "ATTELE", "MONTE"))
            is_auto = is_trot and (q_info['dist'] <= 2150 or "AUTOSTART" in q_info['cond'])

            horses = []
            for p in participants:
                if p.get("statut") == "NON_PARTANT": continue
                num = int(p.get("numPmu", 0))
                drv = str(p.get("driver", "")).upper()
                def_val = str(p.get("deferre", "")).upper()
                is_def = 1 if ("DEFERRE" in def_val or def_val == "TRUE") else 0
                tier = 2 if any(e in drv for e in ELITE_NUMBER_ONE) else (1 if any(s in drv for s in STRONG_DRIVERS) else 0)
                gains = float(p.get("gainsParticipant", {}).get("gainsCarriere", 0))
                draw = int(p.get("placeCorde", num))
                dq, form = analyze_musique(p.get("musique", ""))
                odd = p.get("dernierRapportDirect", {}).get("rapport") or p.get("dernierRapportReference", {}).get("rapport") or 35.0
                horses.append({
                    'num': num, 'nom': p.get("nom", ""), 'drv': drv.split()[-1] if drv else "-",
                    'def': "D" if is_def else "-", 'draw': draw, 'tier': tier,
                    'gains': gains, 'dq': dq, 'form': form, 'odd': float(odd)
                })

            horses.sort(key=lambda x: x['gains'], reverse=True)
            for idx, h in enumerate(horses): h['gains_rank'] = idx + 1
            horses.sort(key=lambda x: x['odd'])
            for idx, h in enumerate(horses): h['odds_rank'] = idx + 1

            for h in horses:
                mkt = (100.0 / (h['odds_rank'] + 1.5)) * 2.5
                sc = (mkt * 0.50) + (h['form'] * 0.65)
                if h['tier'] == 2: sc += 25.0
                elif h['tier'] == 1: sc += 11.0
                if h['gains_rank'] <= 4: sc += 9.0
                if h['dq'] >= 2: sc -= 18.0
                if is_trot:
                    if h['def'] == "D": sc += 8.0
                    if is_auto:
                        if h['draw'] == 8 or h['draw'] == 9: sc -= 10.0
                        elif 10 <= h['draw'] <= 15:
                            front = next((x for x in horses if x['num'] == h['draw'] - 8), None)
                            if front and front['odd'] < 12.0: sc += 18.0
                else:
                    if "PLAT" in q_info['disc'] and q_info['dist'] <= 1800:
                        if 1 <= h['draw'] <= 5: sc += 11.0
                        elif h['draw'] >= 12: sc -= 8.0
                if h['odd'] > 55.0: sc -= 45.0
                h['score'] = round(max(1.0, sc), 1)

            favs = sorted([h for h in horses if h['odd'] <= 19.0], key=lambda x: x['score'], reverse=True)[:4]
            outs = sorted([h for h in horses if 20.0 <= h['odd'] <= 55.0], key=lambda x: x['score'], reverse=True)[:2]
            top6 = sorted(favs + outs, key=lambda x: x['score'], reverse=True)

            if len(top6) < 6:
                rem = sorted([h for h in horses if h not in top6], key=lambda x: x['score'], reverse=True)[:6 - len(top6)]
                top6 = sorted(top6 + rem, key=lambda x: x['score'], reverse=True)

            header = f"{q_info['hippo']} (R{q_info['r']}C{q_info['c']}) | {q_info['disc']} {q_info['dist']}m"
            Clock.schedule_once(lambda dt: self.update_ui(top6, header))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.show_error(f"Error: {str(e)}"))

    def show_error(self, msg):
        self.status_lbl.text = msg

    def update_ui(self, top6, header):
        self.status_lbl.text = header
        nums = " - ".join(str(h['num']) for h in top6)
        self.combo_lbl.text = f"TOP 6:  {nums}"
        for h in top6:
            line = f"#{h['num']}  |  {h['nom']} ({h['drv']})  |  Odd: {h['odd']}  |  Pts: {h['score']}"
            lbl = Label(text=line, font_size="14sp", bold=True, color=(1, 1, 1, 1), size_hint_y=None, height=45)
            self.list_layout.add_widget(lbl)

if __name__ == "__main__":
    QuinteAndroidApp().run()
