"""Local presentation inspired by the current Direct Assurance palette."""

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

CSS = """
:root { --yd-purple: #4c19a1; --yd-ink: #081831; --yd-muted: #62677f; }
body, .nicegui-content { background: #f5f4f9 !important;
  color: var(--yd-ink);
  font-family: "Segoe UI", sans-serif;
  }
.nicegui-content { padding: 0 !important; }
.q-btn { text-transform: none; font-weight: 600; border-radius: 9px; }
.yd-shell { width: 100%; gap: 0 !important; padding: 0; align-items: stretch; }
.yd-header { background: white; border-bottom: 1px solid #e3dfed; width: 100%; }
.yd-banner { max-width: 1168px;
  margin: auto;
  padding: 8px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  }
.yd-banner-text { gap: 12px; align-items: center; }
.yd-brand { display: flex !important;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  color: var(--yd-purple);
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -1.3px;
  line-height: 1.1;
  white-space: nowrap;
  }
.yd-brand-product { color: var(--yd-ink); font-weight: 650; }
.yd-aside { color: var(--yd-ink); font-size: 14px; font-weight: 700; }
.yd-nav { max-width: 1168px;
  margin: 0;
  padding: 0;
  gap: 32px;
  flex-wrap: wrap;
  align-items: center;
  }
.yd-nav a { padding: 20px 0 16px;
  color: #52596d;
  text-decoration: none;
  border-bottom: 3px solid transparent;
  font-size: 14px;
  }
.yd-nav a:hover { color: var(--yd-purple); }
a.yd-nav-on { color: var(--yd-purple); font-weight: 700; border-color: var(--yd-purple); }
a:focus-visible, .q-btn:focus-visible { outline: 3px solid #b7a3d9; outline-offset: 4px; }
.yd-page { width: min(1168px, 100%);
  margin: auto;
  padding: 32px 24px 40px;
  box-sizing: border-box;
  gap: 20px;
  align-items: stretch;
  }
.yd-eyebrow { color: #8061b4; font-size: 12px; font-weight: 700; letter-spacing: 1.5px; }
.yd-page-heading { gap: 8px; margin-bottom: 4px; }
.yd-page-title { font-size: clamp(28px, 3vw, 40px);
  font-weight: 800;
  letter-spacing: -1.2px;
  line-height: 1.15;
  margin: 0;
  }
.yd-title { font-size: 26px; font-weight: 750; line-height: 1.25; margin: 0; }
.yd-lead, .yd-muted { color: var(--yd-muted); font-size: 16px; line-height: 1.6; }
.yd-hint { color: var(--yd-muted); font-size: 13px; line-height: 1.5; }
.yd-section { font-size: 24px; font-weight: 750; margin-top: 6px; }
.yd-section-head { gap: 5px; }
.yd-section-bar { width: 100%;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px 24px;
  flex-wrap: wrap;
  }
.yd-chips { display: grid !important;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  width: 100%;
  }
.yd-chip { background: white;
  border: 1px solid #e3dfed;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  }
.yd-chip-icon { background: #efebfa;
  color: var(--yd-purple);
  padding: 12px;
  border-radius: 50%;
  font-size: 22px;
  }
.yd-chip-copy { gap: 3px; min-width: 0; }
.yd-chip-label { font-size: 14px; font-weight: 700; }
.yd-chip-value { color: var(--yd-muted); font-size: 13px; }
.yd-chip-ok .yd-chip-value { color: #087c56; }
.yd-chip-bad .yd-chip-value { color: #a62939; }
.yd-hero { width: 100%;
  box-sizing: border-box;
  background: #eee8fa;
  border: 1px solid #e8dff7;
  border-radius: 14px;
  padding: 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  }
.yd-hero-copy { gap: 10px; max-width: 780px; }
.yd-hero-icon { color: var(--yd-purple);
  font-size: 78px;
  background: #e6ddf7;
  padding: 22px;
  border-radius: 50%;
  flex-shrink: 0;
  }
.yd-button.q-btn { background: var(--yd-purple) !important;
  color: white !important;
  min-height: 44px;
  padding: 0 24px;
  border-radius: 24px;
  align-self: flex-start;
  }
.yd-button:hover { filter: brightness(1.08); }
.yd-hero .yd-button { margin-top: 6px; }
.yd-wait { flex: 1; width: 100%; min-width: 0; gap: 8px; }
.yd-wait .q-linear-progress { width: 100%; margin-top: 6px; }
.yd-secondary { gap: 12px; flex-wrap: wrap; }
.yd-card-grid { display: grid !important;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  width: 100%;
  gap: 20px;
  align-items: start;
  }
.yd-page .q-card.yd-card { width: 100%;
  min-width: 0;
  background: white;
  border: 1px solid #e3dfed;
  border-radius: 12px;
  box-shadow: none;
  padding: 20px;
  gap: 14px;
  }
.yd-card-top { width: 100%;
  justify-content: space-between;
  align-items: center;
  flex-wrap: nowrap;
  gap: 16px;
  }
.yd-card-id { min-width: 0; gap: 8px; align-items: flex-start; }
.yd-state { width: fit-content;
  min-height: 28px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 750;
  line-height: 1.3;
  }
.yd-state-claimed { background: #e3f5ec; color: #087c56; }
.yd-state-open { background: #ffe8ea; color: #c51829; }
.yd-state-clear { background: #f3f1f7; color: #62677f; }
.yd-when { font-size: 14px; font-weight: 650; color: #555e77; }
.yd-route { color: var(--yd-muted); font-size: 14px; overflow-wrap: anywhere; }
.yd-score-low, .yd-score-ok, .yd-score-unknown { font-weight: 750; font-size: 24px; }
.yd-score { display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: 50%;
  flex-shrink: 0;
  }
.yd-score-low.yd-score { background: #ffe8ea; color: #c51829; }
.yd-score-ok.yd-score { background: #e3f5ec; color: #087c56; }
.yd-score-unknown.yd-score { background: #efebfa; color: var(--yd-purple); font-size: 14px; }
.yd-score-scale { font-size: 11px; font-weight: 600; line-height: 1; }
.yd-card-actions { border-top: 1px solid #eeebf3;
  padding-top: 12px;
  width: 100%;
  gap: 4px;
  align-items: stretch;
  }
.yd-card-links { width: 100%;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  }
.yd-page .q-field { width: 100%; min-width: 0; }
.yd-page .q-field--outlined .q-field__control { border-radius: 8px; background: white; }
.yd-page .q-field__label { color: #62677f; }
.yd-form { width: min(720px, 100%);
  background: white;
  border: 1px solid #e3dfed;
  border-radius: 14px;
  padding: 24px;
  gap: 18px;
  box-sizing: border-box;
  }
.yd-shot { width: 100%;
  max-height: 240px;
  background: #f5f4f9;
  border-radius: 8px;
  }
.yd-shot .q-img__image { object-fit: cover !important;
  object-position: center top !important;
  }
.yd-shot-card { height: 420px; max-height: 420px; }
.yd-shot-open { cursor: zoom-in; }
.yd-shot-link { align-self: flex-start;
  color: var(--yd-purple) !important;
  min-height: 36px;
  padding: 0 8px;
  }
.yd-shot.yd-shot-large { height: min(70vh, 640px); max-height: min(70vh, 640px); }
.yd-shot.yd-shot-large .q-img__image { object-fit: contain !important;
  object-position: center center !important;
  }
.yd-dialog.yd-dialog-shot { width: fit-content;
  max-width: 96vw;
  max-height: 96vh;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px 20px;
  }
.yd-shot-head { position: sticky;
  top: 0;
  z-index: 1;
  width: 100%;
  justify-content: space-between;
  align-items: center;
  flex-wrap: nowrap;
  background: white;
  }
.yd-shot-full { width: auto;
  max-width: min(520px, 92vw);
  max-height: calc(96vh - 120px);
  height: auto;
  object-fit: contain;
  display: block;
  margin: 0 auto;
  border-radius: 8px;
  background: #f5f4f9;
  }
.yd-notice-link { color: var(--yd-purple);
  font-weight: 700;
  white-space: nowrap;
  text-decoration: none;
  }
.yd-claim-list { display: flex !important;
  flex-direction: column;
  width: 100%;
  gap: 12px;
  }
.yd-claim { width: 100%;
  background: white;
  border: 1px solid #e3dfed;
  border-radius: 12px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-sizing: border-box;
  }
.yd-claim .q-btn { align-self: flex-start; }
.yd-notice { width: 100%;
  box-sizing: border-box;
  align-items: center;
  justify-content: space-between;
  flex-wrap: nowrap;
  gap: 12px;
  background: white;
  border: 1px solid #e3dfed;
  border-radius: 10px;
  padding: 10px 8px 10px 18px;
  }
.yd-notice-text { flex: 1; min-width: 0; line-height: 1.45; }
.yd-notice-close.q-btn { color: var(--yd-muted) !important; min-height: 36px; }
.yd-alert { border-left: 4px solid #f71b29; }
.yd-success { border-left: 4px solid #00ac73; }
.yd-empty { width: 100%;
  background: white;
  border: 1px dashed #cfc3e4;
  border-radius: 14px;
  padding: 28px;
  gap: 8px;
  }
.yd-footer { display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-top: 1px solid #e3dfed;
  padding-top: 20px;
  color: var(--yd-muted);
  font-size: 12px;
  }
.yd-dialog { width: min(36rem, 92vw);
  max-width: 92vw;
  padding: 24px;
  border-radius: 14px;
  background: white;
  }
.yd-pre { white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f5f4f9;
  border-radius: 8px;
  padding: 16px;
  line-height: 1.6;
  }
@media (max-width: 800px) {
  .yd-banner { flex-wrap: wrap; padding-top: 18px; gap: 8px; }
  .yd-nav { order: 3; width: 100%; padding: 0; }
  .yd-chips { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .yd-card-grid { grid-template-columns: minmax(0, 1fr); }
  .yd-hero-icon { font-size: 54px; padding: 16px; }
}
@media (max-width: 480px) {
  .yd-banner { padding: 18px 16px 0; gap: 10px; }
  .yd-brand { font-size: 25px; }
  .yd-banner-text { gap: 6px; }
  .yd-aside { font-size: 11px; }
  .yd-nav { padding: 0; gap: 18px; }
  .yd-nav a { font-size: 12px; }
  .yd-page { padding: 24px 16px; gap: 16px; }
  .yd-chip { padding: 12px; gap: 8px; }
  .yd-chip-icon { padding: 8px; font-size: 18px; }
  .yd-hero { padding: 20px; }
  .yd-hero-icon { display: none; }
  .yd-title { font-size: 23px; }
  .yd-form { padding: 18px; }
}
"""


def install_theme() -> None:
    ui.add_head_html("<style>" + CSS + "</style>")
    ui.colors(
        primary="#4c19a1", secondary="#081831", accent="#ffe556",
        positive="#087c56", negative="#c51829",
    )
    ui.dark_mode(False)
    ui.page_title("YouDrive Claimer")


def paint_banner(active: str) -> None:
    with ui.row().classes("yd-banner"):
        with ui.row().classes("yd-banner-text"):
            with ui.element("div").classes("yd-brand"):
                ui.label("YouDrive")
                ui.label("Claimer").classes("yd-brand-product")
        paint_nav(active)
        ui.label("Direct Assurance").classes("yd-aside")


def paint_nav(active: str) -> None:
    items = (
        ("Accueil", "/", "home"),
        ("Trajets", "/trajets", "trips"),
        ("Réclamations", "/reclamations", "claims"),
        ("Réglages", "/reglages", "settings"),
    )
    with ui.element("nav").classes("yd-nav flex").props('aria-label="Navigation principale"'):
        for label, href, key in items:
            link = ui.link(label, href)
            if key == active:
                link.classes("yd-nav-on").props('aria-current="page"')


def page_heading(title: str, detail: str) -> None:
    with ui.column().classes("yd-page-heading"):
        ui.label("MON ESPACE YOUDRIVE").classes("yd-eyebrow")
        ui.label(title).classes("yd-page-title").props('role="heading" aria-level="1"')
        ui.label(detail).classes("yd-lead")


@contextmanager
def shell(active: str) -> Iterator[None]:
    with ui.element("header").classes("yd-header"):
        paint_banner(active)
    with ui.element("main").classes("yd-page flex flex-col"):
        yield
        with ui.element("footer").classes("yd-footer"):
            ui.icon("info_outline")
            ui.label("Aucun message n'est envoyé.")
