"""Flexbar Bridge for Sublime Text 4.

Local authenticated HTTP bridge. No external processes or network calls.
"""
import hashlib
import html
import os
import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import sublime
import sublime_plugin

VERSION = '1.0.0'
SETTINGS_NAME = 'FlexbarBridge.sublime-settings'
CHANGE_KEY = 'FlexbarBridge'

# The bridge keeps German as its backwards-compatible default. Set
# ``"language": "en"`` in FlexbarBridge.sublime-settings for English, or use
# ``"auto"`` to follow Sublime's locale/LC_LANG.
TRANSLATIONS_EN = {
    'Start': 'Start', 'Speichern': 'Save', 'Alles speichern': 'Save All',
    'Rückgängig': 'Undo', 'Wiederholen': 'Redo', 'Befehlspalette': 'Command Palette',
    'Datei öffnen': 'Open File', 'Suche': 'Search', 'Seitenleiste': 'Side Bar',
    'Bearbeiten': 'Edit', 'Zeile dupl.': 'Duplicate Line', 'Kommentar': 'Comment',
    'Blockkommentar': 'Block Comment', 'Einrücken': 'Indent', 'Ausrücken': 'Unindent',
    'Neu formatieren': 'Reindent', 'Zeilen sortieren': 'Sort Lines',
    'Zeilen verbinden': 'Join Lines', 'Navigation': 'Navigation',
    'Datei suchen': 'Goto File', 'Symbol': 'Goto Symbol', 'Zeile': 'Goto Line',
    'Symbol Projekt': 'Goto Symbol in Project', 'Definition': 'Go to Definition',
    'Nächster Treffer': 'Next Result', 'Voriger Treffer': 'Previous Result',
    'Suche in Dateien': 'Find in Files', 'Nächster Tab': 'Next Tab',
    'Voriger Tab': 'Previous Tab', 'Auswahl': 'Selection',
    'Alles markieren': 'Select All', 'Wort markieren': 'Select Word',
    'Zeile markieren': 'Select Line', 'Klammern': 'Select Brackets',
    'Auswahl teilen': 'Split Selection into Lines', 'Mehrfachauswahl': 'Multiple Selection',
    'Kopieren': 'Copy', 'Ausschneiden': 'Cut', 'Einfügen': 'Paste',
    'Projekt': 'Project', 'Build abbrechen': 'Cancel Build',
    'Projekt wechseln': 'Switch Project', 'Schnellaktionen': 'Quick Actions',
    'Konsole': 'Console', 'Zeilenumbruch': 'Word Wrap', 'Automatisch': 'Automatic',
    'Nur Text (kein Symbol)': 'Text Only (no icon)', 'Diskette / Speichern': 'Save',
    'Code formatieren': 'Format Code', 'Plugin': 'Plugin', 'Ordner': 'Folder',
    'Aktualisieren': 'Refresh', 'Terminal': 'Terminal', 'Pfeil links': 'Left Arrow',
    'Pfeil rechts': 'Right Arrow', 'Allgemeine Aktion': 'General Action',
    'Allgemein': 'General', 'Dateien & Ordner': 'Files & Folders',
    'Bearbeiten & Text': 'Editing & Text', 'Navigation & Fenster': 'Navigation & Windows',
    'Suche & Auswahl': 'Search & Selection', 'Code & Entwicklung': 'Code & Development',
    'Git & Versionierung': 'Git & Version Control', 'SFTP & Netzwerk': 'SFTP & Network',
    'Syntax anzeigen': 'Show Syntax', 'Auswahl kopieren': 'Copy Selection',
    'Paket: ': 'Package: ', 'Kontext: ': 'Context: ', 'Format Code': 'Format Code',
    'Flexbar: Menü gespeichert; wird automatisch aktualisiert':
        'Flexbar: menu saved; it will update automatically',
    'Flexbar: plugin command list will be refreshed':
        'Flexbar: plugin command list will be refreshed',
    'Flexbar: keine weiteren Funktionen gefunden':
        'Flexbar: no more functions found',
    'Flexbar: keine weiteren Plugins mit Palette-Befehlen gefunden':
        'Flexbar: no more plugins with palette commands found',
    'Keine zusätzlichen Funktionen verfügbar': 'No additional functions available',
    'Keine zusätzlichen Plugins verfügbar': 'No additional plugins available',
    'Das Plugin ist nicht verfügbar': 'The plugin is not available',
    'Funktion derzeit nicht verfügbar': 'Function currently unavailable',
    'Taste wird aktualisiert': 'Key is being updated',
    'Sublime-Bridge offline': 'Sublime bridge offline',
    'Sublime-Befehl fehlgeschlagen': 'Sublime command failed',
    'TEST-Taste erkannt': 'TEST key detected', 'safe: keine Aktionen': 'safe: no actions',
    'Flexbar Bridge %s': 'Flexbar Bridge %s',
    '✕ Bridge konnte nicht starten (Port %s).': '✕ Bridge could not start (port %s).',
    'Ist der Port belegt? Anderen "port" in den Flexbar-Einstellungen wählen.':
        'Is the port in use? Choose another "port" in the Flexbar settings.',
    'Bridge ist deaktiviert ("enabled": false).': 'Bridge is disabled ("enabled": false).',
    'Bridge läuft auf 127.0.0.1:%s.': 'Bridge is running on 127.0.0.1:%s.',
    'Letzter Kontakt der Flexbar: vor %d s.': 'Last Flexbar contact: %d s ago.',
    'Seit dem Start hat sich die Flexbar noch nicht gemeldet.': 'The Flexbar has not contacted the bridge yet.',
    'Anfragen: %d, ausgeführte Aktionen: %d.': '%d requests, %d actions executed.',
    '● FlexDesigner-Plugin ist verbunden.': '● FlexDesigner plugin is connected.',
    '○ Kein FlexDesigner-Plugin verbunden.': '○ No FlexDesigner plugin connected.',
    'FlexDesigner prüfen bzw. Plugin neu starten:': 'Check FlexDesigner or restart the plugin:',
    'Sublime Text: Flexbar-Menü bearbeiten': 'Sublime Text: Flexbar menu',
    'Sublime Text · Flexbar-Menü': 'Sublime Text · Flexbar menu',
    'Sublime Text: Flexbar-Schnellauswahl': 'Sublime Text: Flexbar quick selection',
    'Sublime Text: Plugin-Befehle aktualisieren': 'Sublime Text: Refresh plugin commands',
    'Sublime Text: Flexbar-Einstellungen': 'Sublime Text: Flexbar settings',
    'Sublime Text: Flexbar-Verbindungsstatus': 'Sublime Text: Flexbar connection status',
    'Flexbar-Menü bearbeiten · Änderungen werden direkt gespeichert und automatisch übernommen.':
        'Flexbar menu · changes are saved and applied automatically.',
    '+ Plugin hinzufügen': '+ Add plugin', 'Standard wiederherstellen': 'Restore defaults',
    'Aktualisieren': 'Refresh', 'Hauptmenü (%d Einträge)': 'Main menu (%d entries)',
    'Noch keine Einträge. Oben eine Funktion oder ein Plugin hinzufügen.':
        'No entries yet. Add a function or plugin above.',
    'Plugin-Untermenü: ': 'Plugin submenu: ', 'Direkte Funktion': 'Direct function',
    'derzeit nicht verfügbar (Taste bleibt grau)': 'currently unavailable (key stays grey)',
    'Symbol: ': 'Icon: ', 'Nach oben verschieben': 'Move up', 'Nach unten verschieben': 'Move down',
    'Aus Menü entfernen': 'Remove from menu', 'Zurück': 'Back', 'Name': 'Name',
    'Entfernen': 'Remove', 'Untermenü bearbeiten': 'Edit submenu',
    'Reihenfolge der Einträge = Reihenfolge auf der Flexbar. Ein Plugin öffnet ein Untermenü. Die sechs festen Aktionsplätze bleiben erhalten.':
        'Entry order = order on the Flexbar. A plugin opens a submenu. The six fixed action slots remain available.',
    'Symbole werden als Material-Design-Icons gezeichnet, nicht als Emoji.':
        'Icons are rendered as Material Design Icons, not emoji.',
    'Plugin nicht verfügbar': 'Plugin unavailable', 'Zurück zum Hauptmenü': 'Back to main menu',
    '‹ Zurück zum Hauptmenü': '‹ Back to main menu', '%d von %d Funktionen ausgewählt': '%d of %d functions selected',
    'Funktionen anzeigen': 'Show functions', 'Alle abwählen': 'Deselect all', 'Alle auswählen': 'Select all',
    'Symbole im Untermenü': 'Submenu icons', 'Alle Symbole ausblenden': 'Hide all icons',
    'Alle Symbole anzeigen': 'Show all icons',
    '[x] schaltet die Funktion ein oder aus. Mit „Symbol wählen“ legst du für jede Funktion ein eigenes Icon fest (auch wenn kein automatisches Icon bekannt ist). „Alle Symbole ausblenden“ betrifft nur die Anzeige, nicht deine Auswahl.':
        '[x] enables or disables the function. Use “Choose icon” to select an icon for each function (even when no automatic icon is known). “Hide all icons” only affects display, not your selection.',
    'Nur Text (manuell)': 'Text only (manual)', 'Manuell: ': 'Manual: ',
    'Automatisch: ': 'Automatic: ', 'Automatisch: kein Symbol verfügbar': 'Automatic: no icon available',
    'Symbol wird angezeigt': 'Icon is shown', 'Text wird angezeigt': 'Text is shown',
    'Symbol wählen': 'Choose icon', 'Symbol ausblenden': 'Hide icon', 'Symbol anzeigen': 'Show icon',
    'Flexbar: Bleibt die Taste leer, kennt das Gerät das Symbol nicht – anderes Symbol, „Nur Text“ oder Eintrag in blocked_icons wählen.':
        'Flexbar: if the key stays empty, the device does not know the icon. Choose another icon, “Text Only”, or add it to blocked_icons.',
    'Fertig': 'Done', 'Auswahl übernehmen und Menü schließen': 'Apply selection and close menu',
    '+ Funktion hinzufügen': '+ Add function', '+ Plugin-Untermenü hinzufügen': '+ Add plugin submenu',
    'Befehl aus Sublime oder installiertem Paket': 'Command from Sublime or an installed package',
    'Zum Beispiel SFTP → Upload / Download': 'For example SFTP → Upload / Download',
    'Auf Standard zurücksetzen': 'Reset to defaults',
    'Speichern, Zeilenumbruch, Einrückung, SFTP (falls installiert)': 'Save, word wrap, indent, SFTP (if installed)',
    'Untermenü': 'Submenu', 'Direkte Funktion': 'Direct function', 'Zurück': 'Back',
    'Nur Text': 'Text only',
    'auswählen zum Verschieben/Entfernen': 'select to move/remove',
    'Flexbar: Menü gestalten': 'Flexbar: edit menu',
    'Funktion suchen und hinzufügen': 'Search and add function',
    'Plugin-Untermenü auswählen': 'Select plugin submenu',
    'Menüeintrag bearbeiten': 'Edit menu entry', 'Keine weiteren Funktionen verfügbar': 'No additional functions available',
    'Funktion suchen…': 'Search for function…', 'Plugin suchen…': 'Search for plugin…',
    'Tastenbeschriftung': 'Key label', 'Symbol suchen, z. B. Umbenennen, Einstellungen, Git…':
        'Search icon, e.g. Rename, Settings, Git…',
    'Symbol suchen, z. B. Zahnrad, Umbenennen, Upload…':
        'Search icon, e.g. Cog, Rename, Upload…',
    'Sublime Text: Die Menükonfiguration auf die Standardauswahl zurücksetzen?':
        'Sublime Text: reset the menu configuration to the default selection?',
}

PHRASES_EN = (
    ('Einstellungen', 'Settings'), ('Dateien', 'Files'), ('Datei', 'File'),
    ('Ordner', 'Folder'), ('Bearbeiten', 'Edit'), ('Text', 'Text'),
    ('Navigation', 'Navigation'), ('Fenster', 'Windows'), ('Suche', 'Search'),
    ('Auswahl', 'Selection'), ('Code', 'Code'), ('Entwicklung', 'Development'),
    ('Versionierung', 'Version Control'), ('Netzwerk', 'Network'),
    ('Speichern', 'Save'), ('Öffnen', 'Open'), ('Löschen', 'Delete'),
    ('Umbenennen', 'Rename'), ('Hinzufügen', 'Add'), ('Entfernen', 'Remove'),
    ('Aktualisieren', 'Refresh'), ('Ausblenden', 'Hide'), ('Anzeigen', 'Show'),
    ('Symbol', 'Icon'), ('Funktion', 'Function'), ('Untermenü', 'Submenu'),
    ('Automatisch', 'Automatic'), ('manuell', 'manual'), ('kein Symbol', 'no icon'),
    ('gesperrt', 'blocked'), ('Alle', 'All'), ('Pfeil', 'Arrow'),
)


def language():
    """Return ``de`` or ``en`` from the bridge setting or Sublime locale."""
    choice = sublime.load_settings(SETTINGS_NAME).get('language', 'de')
    if choice in ('de', 'en'):
        return choice
    locale = sublime.load_settings('Preferences.sublime-settings').get('locale', '')
    locale = str(locale or os.environ.get('LC_ALL') or os.environ.get('LANG') or '').lower()
    return 'de' if locale.startswith('de') else 'en'


def tr(text):
    """Translate a UI label while leaving user/plugin-provided text untouched."""
    if language() != 'en':
        return text
    if text in TRANSLATIONS_EN:
        return TRANSLATIONS_EN[text]
    for german, english in TRANSLATIONS_EN.items():
        if german.endswith(': ') and text.startswith(german):
            return english + text[len(german):]
    for german, english in PHRASES_EN:
        text = text.replace(german, english)
    return text


def tr_format(text, *args):
    return tr(text) % args


COMMANDS = (
    ('Sublime Text: Flexbar-Menü bearbeiten', 'flexbar_bridge_menu_editor'),
    ('Sublime Text: Flexbar-Schnellauswahl', 'flexbar_bridge_configure_menu'),
    ('Sublime Text: Plugin-Befehle aktualisieren', 'flexbar_bridge_reload'),
    ('Sublime Text: Flexbar-Einstellungen', 'flexbar_bridge_open_settings'),
    ('Sublime Text: Flexbar-Verbindungsstatus', 'flexbar_bridge_status'),
)


def write_localized_commands():
    """Create the language-aware Command Palette file in Packages/User."""
    try:
        user_dir = os.path.join(sublime.packages_path(), 'User')
        os.makedirs(user_dir, exist_ok=True)
        path = os.path.join(user_dir, 'FlexbarBridge.sublime-commands')
        data = [{'caption': tr(caption), 'command': command} for caption, command in COMMANDS]
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
    except Exception as exc:
        print('FlexbarBridge command localization failed:', repr(exc))


def settings_changed():
    write_localized_commands()
    bump_menu()


def package_group(name):
    return tr('Paket: ') + name


def is_package_group(name):
    return isinstance(name, str) and name.startswith(tr('Paket: '))


def package_name(name):
    prefix = tr('Paket: ')
    return name[len(prefix):]
SERVER = None
THREAD = None
# 'at' == 0 means "must rescan"; 'checked' throttles the cheap fingerprint test.
CACHE = {'at': 0, 'checked': 0, 'fingerprint': None, 'package_groups': []}
CACHE_LOCK = threading.RLock()
STATE_LOCK = threading.RLock()
ACTION_LOOKUP = {}

# Long-poll support: the FlexDesigner plugin waits on /v1/menu until the menu
# changes, so updates arrive immediately and an idle Sublime does no work.
MENU_COND = threading.Condition()
MENU_EPOCH = 0
SHUTDOWN = threading.Event()
MAX_WAIT_SECONDS = 25      # upper bound for a single long-poll request
RECHECK_SECONDS = 10       # safety re-evaluation while waiting (missed events)
FINGERPRINT_SECONDS = 5    # how often the installed-package list is compared
PACKAGE_RESCAN_SECONDS = 300  # full rescan even without a detected change

# Status bar indicator: shows that the bridge is loaded and whether the
# FlexDesigner plugin is talking to it. Only timestamps are recorded here (from
# HTTP worker threads); the status bar itself is updated on the main thread.
STATUS_KEY = 'zz_flexbar_bridge'   # 'zz' keeps it at the right end of the status bar
CLIENT_TIMEOUT_SECONDS = 45        # long-poll answers at least every ~20 s
ACTIVITY_SECONDS = 1.5             # how long the "data exchanged" mark stays visible
STATUS_TICK_MS = 2000
STATUS_LOCK = threading.Lock()
STATUS = {'running': False, 'error': None, 'port': None, 'started': 0.0,
          'last_seen': 0.0, 'activity': 0.0, 'waiting': 0, 'requests': 0,
          'actions': 0, 'shown': None, 'generation': 0}

# Only commands from the active Sublime Text installation are exposed.
# All commands require an actual touch on the Flexbar.
CORE = [
    ('Start', [
        ('Speichern', 'save', {}),
        ('Alles speichern', 'save_all', {}),
        ('Rückgängig', 'undo', {}),
        ('Wiederholen', 'redo', {}),
        ('Befehlspalette', 'show_overlay', {'overlay': 'command_palette'}),
        ('Datei öffnen', 'show_overlay', {'overlay': 'goto', 'text': ''}),
        ('Suche', 'show_panel', {'panel': 'find'}),
        ('Seitenleiste', 'toggle_side_bar', {}),
    ]),
    ('Bearbeiten', [
        ('Zeile dupl.', 'duplicate_line', {}),
        ('Kommentar', 'toggle_comment', {'block': False}),
        ('Blockkommentar', 'toggle_comment', {'block': True}),
        ('Einrücken', 'indent', {}),
        ('Ausrücken', 'unindent', {}),
        ('Neu formatieren', 'reindent', {}),
        ('Zeilen sortieren', 'sort_lines', {'case_sensitive': False}),
        ('Zeilen verbinden', 'join_lines', {}),
    ]),
    ('Navigation', [
        ('Datei suchen', 'show_overlay', {'overlay': 'goto', 'text': ''}),
        ('Symbol', 'show_overlay', {'overlay': 'goto', 'text': '@'}),
        ('Zeile', 'show_overlay', {'overlay': 'goto', 'text': ':'}),
        ('Symbol Projekt', 'goto_symbol_in_project', {}),
        ('Definition', 'goto_definition', {}),
        ('Nächster Treffer', 'find_next', {}),
        ('Voriger Treffer', 'find_prev', {}),
        ('Suche in Dateien', 'show_panel', {'panel': 'find_in_files'}),
        ('Nächster Tab', 'next_view', {}),
        ('Voriger Tab', 'prev_view', {}),
    ]),
    ('Auswahl', [
        ('Alles markieren', 'select_all', {}),
        ('Wort markieren', 'expand_selection', {'to': 'word'}),
        ('Zeile markieren', 'expand_selection', {'to': 'line'}),
        ('Klammern', 'expand_selection', {'to': 'brackets'}),
        ('Auswahl teilen', 'split_selection_into_lines', {}),
        ('Mehrfachauswahl', 'find_under_expand', {}),
        ('Kopieren', 'copy', {}),
        ('Ausschneiden', 'cut', {}),
        ('Einfügen', 'paste', {}),
    ]),
    ('Projekt', [
        ('Build', 'build', {}),
        ('Build abbrechen', 'cancel_build', {}),
        ('Projekt wechseln', 'prompt_select_project', {}),
        ('Schnellaktionen', 'show_overlay', {'overlay': 'command_palette'}),
        ('Konsole', 'show_panel', {'panel': 'console'}),
        ('Zeilenumbruch', 'toggle_setting', {'setting': 'word_wrap'}),
    ]),
]


# Material Design Icons are rendered by FlexDesigner; no Unicode symbols in hardware titles.
ICONS = [
    ('Automatisch', None),
    ('Nur Text (kein Symbol)', '__text__'),
    ('Diskette / Speichern', 'mdi mdi-content-save'),
    ('Zeilenumbruch / Return', 'mdi mdi-keyboard-return'),
    ('Code formatieren', 'mdi mdi-code-braces'),
    ('Upload', 'mdi mdi-cloud-upload'),
    ('Download', 'mdi mdi-cloud-download'),
    ('SFTP / Cloud', 'mdi mdi-cloud-outline'),
    ('Plugin', 'mdi mdi-puzzle'),
    ('Ordner', 'mdi mdi-folder-outline'),
    ('Git', 'mdi mdi-source-branch'),
    ('Suche', 'mdi mdi-magnify'),
    ('Kommentar', 'mdi mdi-comment-text-outline'),
    ('Kopieren', 'mdi mdi-content-copy'),
    ('Build / Werkzeug', 'mdi mdi-hammer-wrench'),
    ('Aktualisieren', 'mdi mdi-refresh'),
    ('Terminal', 'mdi mdi-console'),
    ('Pfeil links', 'mdi mdi-arrow-left'),
    ('Pfeil rechts', 'mdi mdi-arrow-right'),
    ('Allgemeine Aktion', 'mdi mdi-lightning-bolt'),
]

# Erweiterte, bewusst kuratierte Material-Design-Icons-Sammlung.
# Einzeilige Quick-Panel-Einträge sind direkt per Tastatur durchsuchbar:
# nach Kategorie, Funktionsname oder MDI-Bezeichner.
# Frühere ICONS bleiben mit identischen Bezeichnern erhalten.
ICON_GROUPS = [
    ('Allgemein', [
        ('Einstellungen / Zahnrad', 'cog'),
        ('Einstellungen (Kontur)', 'cog-outline'),
        ('Mehrere Einstellungen', 'cogs'),
        ('Werkzeuge', 'tools'),
        ('Optionen / Regler', 'tune'),
        ('Information', 'information-outline'),
        ('Hilfe', 'help-circle-outline'),
        ('Über / Info', 'information'),
        ('Warnung', 'alert-outline'),
        ('Fehler / Warnung', 'alert-circle-outline'),
        ('Erfolg / Bestätigung', 'check-circle-outline'),
        ('Abbrechen / X', 'close'),
        ('Hinzufügen / Plus', 'plus'),
        ('Entfernen / Minus', 'minus'),
        ('Löschen / Papierkorb', 'delete-outline'),
        ('Aktivieren / Haken', 'check'),
        ('Sichtbar / Auge', 'eye-outline'),
        ('Ausblenden / Auge durchgestrichen', 'eye-off-outline'),
        ('Favorit / Stern', 'star-outline'),
        ('Benachrichtigung / Glocke', 'bell-outline'),
    ]),
    ('Dateien & Ordner', [
        ('Neue Datei', 'file-plus-outline'),
        ('Datei', 'file-outline'),
        ('Datei bearbeiten', 'file-edit-outline'),
        ('Datei umbenennen', 'rename-box'),
        ('Datei löschen', 'file-remove-outline'),
        ('Datei suchen', 'file-search-outline'),
        ('Datei prüfen', 'file-check-outline'),
        ('Datei verschieben', 'file-move-outline'),
        ('Datei duplizieren', 'file-multiple-outline'),
        ('Dateien speichern', 'content-save-all'),
        ('Speichern (Kontur)', 'content-save-outline'),
        ('Import', 'file-import-outline'),
        ('Export', 'file-export-outline'),
        ('Datei wiederherstellen', 'file-restore-outline'),
        ('Datei mit Code', 'file-code-outline'),
        ('Ordner', 'folder'),
        ('Ordner öffnen', 'folder-open-outline'),
        ('Ordner erstellen', 'folder-plus-outline'),
        ('Ordner löschen', 'folder-remove-outline'),
        ('Ordner suchen', 'folder-search-outline'),
        ('Ordner konfigurieren', 'folder-cog-outline'),
        ('Mehrere Ordner', 'folder-multiple-outline'),
    ]),
    ('Bearbeiten & Text', [
        ('Umbenennen', 'rename'),
        ('Umbenennen (Feld)', 'rename-box-outline'),
        ('Bearbeiten / Stift', 'pencil'),
        ('Bearbeiten (Kontur)', 'pencil-outline'),
        ('Ausschneiden / Schere', 'content-cut'),
        ('Einfügen / Paste', 'content-paste'),
        ('Rückgängig / Undo', 'undo'),
        ('Wiederholen / Redo', 'redo'),
        ('Kopieren / Duplizieren', 'content-duplicate'),
        ('Text markieren', 'select-all'),
        ('Text', 'format-text'),
        ('Fett', 'format-bold'),
        ('Kursiv', 'format-italic'),
        ('Unterstreichen', 'format-underline'),
        ('Durchstreichen', 'format-strikethrough'),
        ('Text linksbündig', 'format-align-left'),
        ('Text zentrieren', 'format-align-center'),
        ('Text rechtsbündig', 'format-align-right'),
        ('Einrückung erhöhen', 'format-indent-increase'),
        ('Einrückung verringern', 'format-indent-decrease'),
        ('Aufzählung', 'format-list-bulleted'),
        ('Nummerierte Liste', 'format-list-numbered'),
        ('Sortieren A–Z', 'sort-alphabetical-ascending'),
        ('Sortieren Z–A', 'sort-alphabetical-descending'),
        ('Zitate', 'format-quote-open'),
        ('Zwischenablage', 'clipboard-outline'),
        ('Zwischenablage (Text)', 'clipboard-text-outline'),
        ('Text bereinigen / Radierer', 'eraser'),
    ]),
    ('Navigation & Fenster', [
        ('Startseite / Home', 'home-outline'),
        ('Zurück (Chevron)', 'chevron-left'),
        ('Weiter (Chevron)', 'chevron-right'),
        ('Nach oben', 'arrow-up'),
        ('Nach unten', 'arrow-down'),
        ('Zurück im Kreis', 'arrow-left-circle-outline'),
        ('Vorwärts im Kreis', 'arrow-right-circle-outline'),
        ('Menü / Hamburger', 'menu'),
        ('Menü öffnen', 'menu-open'),
        ('Mehr / horizontal', 'dots-horizontal'),
        ('Mehr / vertikal', 'dots-vertical'),
        ('In neuem Fenster öffnen', 'open-in-new'),
        ('Link / Verknüpfung', 'link-variant'),
        ('Tab / Register', 'tab'),
        ('Neuer Tab', 'tab-plus'),
        ('Tab schließen', 'tab-remove'),
        ('Fenster maximieren', 'window-maximize'),
        ('Fenster minimieren', 'window-minimize'),
        ('Seitenleiste / Ansicht', 'view-list-outline'),
        ('Kachelansicht', 'view-grid-outline'),
        ('Dashboard', 'view-dashboard-outline'),
        ('Bildschirm', 'monitor'),
        ('Historie', 'history'),
    ]),
    ('Suche & Auswahl', [
        ('Suchen (groß)', 'magnify'),
        ('Hineinzoomen', 'magnify-plus-outline'),
        ('Herauszoomen', 'magnify-minus-outline'),
        ('Suchen und Ersetzen', 'find-replace'),
        ('Filter', 'filter-outline'),
        ('Filter entfernen', 'filter-remove-outline'),
        ('Lesezeichen', 'bookmark-outline'),
        ('Lesezeichen hinzufügen', 'bookmark-plus-outline'),
        ('Markierung / Pin', 'pin-outline'),
        ('Auswahl / Checkbox', 'checkbox-marked-outline'),
        ('Auswahl / leeres Kästchen', 'checkbox-blank-outline'),
        ('Mehrfachauswahl', 'checkbox-multiple-marked-outline'),
        ('Mauszeiger', 'cursor-default'),
        ('Mausklick', 'cursor-default-click'),
        ('Tastatur', 'keyboard'),
        ('Tab-Taste', 'keyboard-tab'),
        ('Backspace', 'keyboard-backspace'),
        ('ESC', 'keyboard-esc'),
    ]),
    ('Code & Entwicklung', [
        ('Code / Tags', 'code-tags'),
        ('Code / Klammern', 'code-brackets'),
        ('JSON', 'code-json'),
        ('XML', 'xml'),
        ('Regulärer Ausdruck / Regex', 'regex'),
        ('Programmiersprache Python', 'language-python'),
        ('Programmiersprache JavaScript', 'language-javascript'),
        ('Programmiersprache PHP', 'language-php'),
        ('HTML', 'language-html5'),
        ('CSS', 'language-css3'),
        ('Terminal / Konsole', 'console-line'),
        ('Debuggen / Käfer', 'bug-outline'),
        ('Build / Hammer', 'hammer'),
        ('Werkzeug / Schraubenschlüssel', 'wrench'),
        ('Ausführen / Play', 'play'),
        ('Ausführen (Kreis)', 'play-circle-outline'),
        ('Stoppen', 'stop'),
        ('Pause', 'pause'),
        ('Neustarten', 'restart'),
        ('Test / Reagenzglas', 'test-tube'),
        ('Paket / Plugin (Kontur)', 'puzzle-outline'),
        ('API', 'api'),
        ('Datenbank', 'database-outline'),
        ('Webseite', 'web'),
        ('Server', 'server'),
        ('Docker', 'docker'),
    ]),
    ('Git & Versionierung', [
        ('Git-Logo', 'git'),
        ('GitHub', 'github'),
        ('Branch', 'source-branch'),
        ('Commit', 'source-commit'),
        ('Merge', 'source-merge'),
        ('Pull', 'source-pull'),
        ('Branch vergleichen', 'compare'),
        ('Fork', 'source-fork'),
        ('Repository', 'source-repository'),
        ('Git-Änderungen', 'file-compare'),
        ('Verlauf', 'history'),
        ('Aktualisieren / Sync', 'sync'),
    ]),
    ('SFTP & Netzwerk', [
        ('Cloud', 'cloud-outline'),
        ('Cloud Upload (Kontur)', 'cloud-upload-outline'),
        ('Cloud Download (Kontur)', 'cloud-download-outline'),
        ('Cloud synchronisieren', 'cloud-sync-outline'),
        ('Cloud aktualisieren', 'cloud-refresh-outline'),
        ('Cloud verbunden', 'cloud-check-outline'),
        ('Upload (Pfeil)', 'upload'),
        ('Download (Pfeil)', 'download'),
        ('Daten übertragen', 'transfer'),
        ('Tauschen / links rechts', 'swap-horizontal'),
        ('Tauschen / oben unten', 'swap-vertical'),
        ('Synchronisierung', 'sync'),
        ('Wiederholen / Aktualisieren', 'reload'),
        ('Netzwerk', 'lan'),
        ('Netzwerk verbunden', 'lan-connect'),
        ('Netzwerk getrennt', 'lan-disconnect'),
        ('WLAN', 'wifi'),
        ('WLAN aus', 'wifi-off'),
        ('Schloss', 'lock-outline'),
        ('Schloss offen', 'lock-open-outline'),
        ('Sicherheit', 'shield-check-outline'),
    ]),
]
# Die ursprüngliche Basisliste (ältere MDI-Versionen kennen diese Symbole sicher).
BASE_ICONS = frozenset(value for _, value in ICONS if value and value != '__text__')
# Basisicons behalten Vorrang (auch bei späteren Doppelungen).
_existing_icon_values = {value for _, value in ICONS if value}
for _category, _options in ICON_GROUPS:
    for _caption, _mdi_name in _options:
        _value = 'mdi mdi-' + _mdi_name
        if _value not in _existing_icon_values:
            ICONS.append((_category + ' · ' + _caption, _value))
            _existing_icon_values.add(_value)
# Keine Kategorie-/Platzhalter-Einträge als Icon durchreichen.
del _existing_icon_values, _category, _options, _caption, _mdi_name, _value

KNOWN_ICONS = {value for _, value in ICONS if value and value != '__text__'}
ICON_LABELS = {value: label for label, value in ICONS if value}

def blocked_icons():
    """Icons the user excluded because the device's MDI version does not know them.

    The setting ``blocked_icons`` accepts ``"cog"``, ``"mdi-cog"`` or ``"mdi mdi-cog"``.
    """
    raw = sublime.load_settings(SETTINGS_NAME).get('blocked_icons', [])
    blocked = set()
    if isinstance(raw, list):
        for name in raw:
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            if name.startswith('mdi mdi-'):
                blocked.add(name)
            else:
                blocked.add('mdi mdi-' + (name[4:] if name.startswith('mdi-') else name))
    return blocked


def icon_blocked(value):
    return bool(value) and value in blocked_icons()


def icon_picker_rows(current=None):
    """Searchable labels with icon IDs, shared by main and package submenus."""
    blocked = blocked_icons()
    return [
        tr(label) + ('  —  ' + icon[4:] if icon and icon.startswith('mdi ') else '')
        + ('  ✓' if icon == current else '')
        + ('  (gesperrt)' if icon in blocked else '')
        for label, icon in ICONS
    ]


def icon_hint(icon):
    """Tell the user how to recover if the device does not know a newer icon."""
    if icon and icon != '__text__' and icon not in BASE_ICONS:
        sublime.status_message(tr('Flexbar: Bleibt die Taste leer, kennt das Gerät das Symbol nicht – '
                               'anderes Symbol, „Nur Text“ oder Eintrag in blocked_icons wählen.'))


def choose_icon(selected, suggested):
    # Explicit opt-out wins over both manual and suggested icons.
    value = selected.get('icon')
    if value == '__text__': return None
    blocked = blocked_icons()
    if value in KNOWN_ICONS and value not in blocked: return value
    return suggested if suggested in KNOWN_ICONS and suggested not in blocked else None

def suggested_icon(command='', args=None, label='', group=''):
    command = str(command).lower()
    label = str(label).lower()
    group = str(group).lower()
    args = args or {}
    if command in ('save', 'save_all') or 'speichern' in label or 'save ' in label:
        return 'mdi mdi-content-save'
    if (command == 'toggle_setting' and args.get('setting') == 'word_wrap') or any(
            name in label for name in ('zeilenumbruch', 'word wrap', 'line wrap')):
        return 'mdi mdi-keyboard-return'
    if any(name in label for name in ('format', 'reindent', 'einrückung', 'indent')):
        return 'mdi mdi-code-braces'
    if 'upload' in command or 'upload' in label: return 'mdi mdi-cloud-upload'
    if 'download' in command or 'download' in label: return 'mdi mdi-cloud-download'
    if any(x in label or x in command for x in ('umbenenn', 'rename')):
        return 'mdi mdi-rename-box'
    if any(x in label for x in ('einstellungen', 'settings', 'preferences', 'configuration', 'configure', 'konfiguration', 'konfigurieren')) or 'settings' in command or 'preferences' in command:
        return 'mdi mdi-cog'
    if 'sftp' in group or 'sftp' in label: return 'mdi mdi-cloud-outline'
    if 'git' in group or 'git' in label: return 'mdi mdi-source-branch'
    if 'search' in label or 'suche' in label or 'find' in command: return 'mdi mdi-magnify'
    if 'comment' in command or 'kommentar' in label: return 'mdi mdi-comment-text-outline'
    if 'copy' in command or 'kopieren' in label: return 'mdi mdi-content-copy'
    if 'build' in command or 'build' in label: return 'mdi mdi-hammer-wrench'
    if 'console' in command or 'terminal' in label: return 'mdi mdi-console'
    return None  # Unknown commands display their label rather than a generic icon.

def action_id(command, args, namespace):
    encoded = json.dumps([namespace, command, args], ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]


def make_action(label, command, args, namespace, enabled=True):
    return {'id': action_id(command, args, namespace), 'label': tr(label)[:54],
            'command': command, 'args': args, 'origin': namespace,
            'icon': suggested_icon(command,args,label,namespace),
            'enabled': bool(enabled)}


def read_package_commands():
    """Read Command Palette resources, including commands installed by plugins."""
    groups = {}
    ignored = set(sublime.load_settings('Preferences.sublime-settings').get('ignored_packages', []))
    for path in sublime.find_resources('*.sublime-commands'):
        bits = path.split('/')
        if len(bits) < 3 or bits[0] != 'Packages':
            continue
        name = bits[1]
        if name in ('Default', 'FlexbarBridge') or name in ignored or bits[-1] == 'FlexbarBridge.sublime-commands':
            continue
        try:
            items = sublime.decode_value(sublime.load_resource(path, max_size=300000))
        except (Exception,):
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            cmd, label, args = item.get('command'), item.get('caption'), item.get('args', {})
            if not isinstance(cmd, str) or not isinstance(label, str) or not isinstance(args, dict):
                continue
            if not cmd.strip() or not label.strip():
                continue
            # Do not duplicate identical definitions that are present in several menus.
            group = groups.setdefault(name, {})
            action = make_action(re.sub(r'\s+', ' ', label).strip(), cmd, args, name)
            group[action['id']] = action
    return [{'name': package_group(name), 'actions': list(actions.values())[:72]}
            for name, actions in sorted(groups.items(), key=lambda x: x[0].casefold())
            if actions]


def _package_fingerprint():
    """Cheap signature of which palette files exist and which packages are ignored."""
    ignored = sublime.load_settings('Preferences.sublime-settings').get('ignored_packages', [])
    return (tuple(sorted(sublime.find_resources('*.sublime-commands'))),
            tuple(sorted(str(x) for x in ignored)))


def package_groups_cached():
    """Rescan palette files only when something actually changed.

    Contents are re-read when the file list or ignored packages change, when a
    .sublime-commands file is saved, on explicit refresh, or every five minutes.
    """
    with CACHE_LOCK:
        now = time.monotonic()
        stale = CACHE['at'] == 0 or now - CACHE['at'] > PACKAGE_RESCAN_SECONDS
        if not stale and now - CACHE['checked'] > FINGERPRINT_SECONDS:
            CACHE['checked'] = now
            stale = CACHE['fingerprint'] != _package_fingerprint()
        if stale:
            CACHE['fingerprint'] = _package_fingerprint()
            CACHE['package_groups'] = read_package_commands()
            CACHE['at'] = CACHE['checked'] = now
        return list(CACHE['package_groups'])


def menu_version(items):
    """Short stable fingerprint of the visible menu (labels, icons, availability)."""
    encoded = json.dumps(items, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return hashlib.sha1(encoded.encode('utf-8')).hexdigest()[:16]


def bump_menu(*_unused):
    """Wake long-polling clients so they re-evaluate the menu right now."""
    global MENU_EPOCH
    with MENU_COND:
        MENU_EPOCH += 1
        MENU_COND.notify_all()


def invalidate_package_cache():
    with CACHE_LOCK:
        CACHE['at'] = 0
    bump_menu()


def build_state():
    window = sublime.active_window()
    view = window.active_view() if window else None
    syntax = ''
    selected = False
    if view:
        syntax = (view.settings().get('syntax') or '').rsplit('/', 1)[-1].replace('.sublime-syntax', '')
        selected = any(not region.empty() for region in view.sel())
    groups = []
    for name, definitions in CORE:
        actions = [make_action(label, command, args, 'core')
                   for label, command, args in definitions
                   ]
        groups.append({'name': tr(name), 'actions': actions})

    # Context-sensitive options depend on the active document. They are always
    # listed; unavailable ones are flagged instead of vanishing, so keys on the
    # Flexbar never shift position while you work.
    has_view = bool(view)
    context_actions = [make_action('Syntax anzeigen', 'show_scope_name', {}, 'context', has_view),
                       make_action('Autocomplete', 'auto_complete', {}, 'context', has_view)]
    if has_view and syntax.lower() in ('python', 'javascript', 'typescript', 'php', 'html', 'css', 'json'):
        context_actions.extend([make_action('Kommentar', 'toggle_comment', {'block': False}, 'context'),
                                make_action('Definition', 'goto_definition', {}, 'context')])
    context_actions.append(make_action('Auswahl kopieren', 'copy', {}, 'context', selected))
    groups.insert(1, {'name': tr('Kontext: ') + (syntax or 'Text'), 'actions': context_actions})

    # Opt-in commands for packages without Command Palette entries.
    customs = sublime.load_settings(SETTINGS_NAME).get('custom_commands', [])
    custom_groups = {}
    if isinstance(customs, list):
        for item in customs[:80]:
            if not isinstance(item, dict):
                continue
            name, label, command, args = (item.get('group', 'Eigene Aktionen'),
                                          item.get('label'), item.get('command'),
                                          item.get('args', {}))
            if not all(isinstance(v, str) and v.strip() for v in (name, label, command)) or not isinstance(args, dict):
                continue
            custom_groups.setdefault(name[:54], []).append(make_action(label, command, args, 'custom'))
        groups.extend({'name': name, 'actions': actions} for name, actions in custom_groups.items())
    groups.extend(package_groups_cached())
    with STATE_LOCK:
        ACTION_LOOKUP.clear()
        for group in groups:
            for action in group['actions']:
                ACTION_LOOKUP[action['id']] = {'command': action['command'], 'args': action['args'],
                                               'enabled': action.get('enabled', True)}
    # No document contents or absolute file paths are transmitted.
    return {'online': True, 'syntax': syntax, 'selection': selected,
            'dirty': bool(view.is_dirty()) if view else False,
            'has_view': bool(view), 'groups': groups}



# Only opted-in actions and their explicitly selected package submenus are
# delivered to the Flexbar. The full catalogue stays inside Sublime Text.
def default_menu_entries(catalogue):
    all_actions = [a for g in catalogue['groups'] for a in g['actions']]
    chosen = []
    for cmd, args, title in [
        ('save', {}, 'Speichern'),
        ('toggle_setting', {'setting': 'word_wrap'}, 'Zeilenumbruch'),
        ('reindent', {}, 'Einrückung')]:
        action = next((a for a in all_actions
                       if a['command'] == cmd and a['args'] == args and a['origin'] == 'core'), None)
        if action:
            chosen.append({'type': 'action', 'id': action['id'], 'label': title})
    # Prefer a real formatter if one is exposed by an installed package.
    formatter = next((a for a in all_actions
                      if any(term in a['label'].lower() for term in
                             ('format document', 'format code', 'code formatter'))
                      and not any(term in a['label'].lower() for term in
                                  ('on save', 'settings', 'toggle'))), None)
    if formatter:
        chosen = [e for e in chosen if e.get('label') != 'Einrückung']
        chosen.append({'type': 'action', 'id': formatter['id'], 'label': 'Format Code'})
    if any(g['name'] == package_group('SFTP') for g in catalogue['groups']):
        chosen.append({'type': 'package', 'name': 'SFTP'})
    return chosen


def configured_entries(catalogue):
    raw = sublime.load_settings(SETTINGS_NAME).get('menu_items', None)
    if raw is None:
        return default_menu_entries(catalogue)
    return raw[:80] if isinstance(raw, list) else []


def submenu_icon_override(entry, action_id_value):
    """Validated manual choice: None (automatic), __text__, or an MDI icon."""
    overrides = entry.get('sub_icon_overrides', {})
    value = overrides.get(action_id_value) if isinstance(overrides, dict) else None
    return value if isinstance(value, str) and (value == '__text__' or value in KNOWN_ICONS) else None


def submenu_icon_visible(entry, action_id_value):
    visible = entry.get('sub_icons') != 'text'
    toggles = entry.get('icon_toggle_ids', [])
    if isinstance(toggles, list) and action_id_value in toggles:
        visible = not visible
    return visible


def set_submenu_icon(entry, action_id_value, choice):
    """Apply an explicit per-command choice without changing other commands.

    The global show/hide buttons affect visibility only. Choosing a concrete
    icon makes this command visible even when the submenu default is text.
    """
    if choice is not None and choice != '__text__' and choice not in KNOWN_ICONS:
        raise ValueError('Unknown icon')
    stored = entry.get('sub_icon_overrides', {})
    stored = dict(stored) if isinstance(stored, dict) else {}
    if choice is None:
        stored.pop(action_id_value, None)
    else:
        stored[action_id_value] = choice
    if stored:
        entry['sub_icon_overrides'] = stored
    else:
        entry.pop('sub_icon_overrides', None)
    if choice in KNOWN_ICONS:
        # Explicitly selected icons should be visible immediately.
        toggles = entry.get('icon_toggle_ids', [])
        toggles = set(toggles) if isinstance(toggles, list) else set()
        global_visible = entry.get('sub_icons') != 'text'
        if global_visible:
            toggles.discard(action_id_value)
        else:
            toggles.add(action_id_value)
        if toggles:
            entry['icon_toggle_ids'] = sorted(toggles)
        else:
            entry.pop('icon_toggle_ids', None)


def submenu_icon(entry, action):
    """Manual icon (or explicit text) with independent visibility controls."""
    choice = submenu_icon_override(entry, action['id'])
    if choice == '__text__' or not submenu_icon_visible(entry, action['id']):
        return None
    blocked = blocked_icons()
    for candidate in (choice, action.get('icon')):
        if candidate in KNOWN_ICONS and candidate not in blocked:
            return candidate
    return None


def submenu_selected_ids(entry, actions):
    """All actions are selected until action_ids is explicitly saved."""
    ids = entry.get('action_ids')
    available = {a['id'] for a in actions}
    if isinstance(ids, list):
        return {aid for aid in ids if isinstance(aid, str) and aid in available}
    return available


def build_menu_state():
    catalogue = build_state()
    by_id = {a['id']: a for g in catalogue['groups'] for a in g['actions']}
    by_package = {package_name(g['name']): g['actions'] for g in catalogue['groups']
                  if is_package_group(g['name'])}
    result = []
    for selected in configured_entries(catalogue):
        if not isinstance(selected, dict):
            continue
        if selected.get('type') == 'action':
            a = by_id.get(selected.get('id'))
            if a:
                stored_label = str(selected.get('label') or a['label'])
                result.append({'type': 'action', 'id': a['id'],
                               'label': tr(stored_label)[:54],
                               'icon': choose_icon(selected, a['icon']),
                               'enabled': a.get('enabled', True)})
            elif isinstance(selected.get('id'), str) and re.fullmatch(r'[0-9a-f]{24}', selected['id']):
                # Not available right now (context command, package disabled, ...):
                # keep the slot, greyed out, so the other keys do not move.
                result.append({'type': 'action', 'id': selected['id'],
                               'label': tr(str(selected.get('label') or 'Aktion'))[:54],
                               'icon': choose_icon(selected, None),
                               'enabled': False})
        elif selected.get('type') == 'package':
            name = selected.get('name')
            actions = by_package.get(name) if isinstance(name, str) else None
            if actions:
                allow = submenu_selected_ids(selected, actions)
                actions = [a for a in actions if a['id'] in allow]
                if not actions: continue
                result.append({'type': 'menu', 'id': 'package:' + name,
                               'label': str(selected.get('label') or name)[:54],
                               'icon': choose_icon(selected,
                                       'mdi mdi-cloud-outline' if name.casefold() == 'sftp' else 'mdi mdi-puzzle'),
                               'items': [{'type': 'action', 'id': a['id'],
                                          'icon': submenu_icon(selected, a),
                                          'label': (a['label'][len(name)+2:]
                                                    if a['label'].startswith(name+': ') else a['label'])}
                                         for a in actions]})
    return {'online': True, 'schema': 3, 'version': menu_version(result), 'items': result}


def state_on_main_thread(timeout=2.5, builder=build_state):
    """Read Sublime state on the UI thread; HTTP handlers are worker threads.

    set_timeout enqueues work on Sublime's main thread. The worker waits for a
    bounded period and never accesses window/view APIs itself.
    """
    completed = threading.Event()
    result = {}

    def capture():
        try:
            result['state'] = builder()
        except Exception as exc:
            result['error'] = exc
        finally:
            completed.set()

    sublime.set_timeout(capture, 0)
    if not completed.wait(timeout):
        raise TimeoutError('Sublime main thread not responding')
    if 'error' in result:
        raise result['error']
    return result['state']

def wait_for_menu_change(known_version, timeout):
    """Block until the menu differs from ``known_version``; None on timeout/shutdown.

    The menu is evaluated on the UI thread, then the worker sleeps on a condition
    that Sublime events (focus, selection flip, saves, settings) wake up.
    """
    deadline = time.monotonic() + timeout
    while True:
        with MENU_COND:
            epoch = MENU_EPOCH
        state = state_on_main_thread(builder=build_menu_state)
        if state['version'] != known_version:
            return state
        remaining = deadline - time.monotonic()
        if remaining <= 0 or SHUTDOWN.is_set():
            return None
        with MENU_COND:
            # An event between evaluation and wait changes the epoch: no lost wake-up.
            if MENU_EPOCH == epoch and not SHUTDOWN.is_set():
                MENU_COND.wait(min(remaining, RECHECK_SECONDS))


def execute_action(action_id_value):
    # Invoke on the Sublime main thread, never from the HTTP worker.
    with STATE_LOCK:
        action = ACTION_LOOKUP.get(action_id_value)
    if action is None or not action.get('enabled', True):
        return False
    window = sublime.active_window()
    if not window:
        return False
    window.run_command(action['command'], action['args'])
    return True


def note_client(activity=False, action=False):
    """Record an authenticated request (called from HTTP worker threads)."""
    now = time.time()
    with STATUS_LOCK:
        STATUS['last_seen'] = now
        STATUS['requests'] += 1
        if action:
            STATUS['actions'] += 1
        if activity or action:
            STATUS['activity'] = now
    if activity or action:
        _schedule_status_refresh()


def _client_waiting(delta):
    with STATUS_LOCK:
        STATUS['waiting'] = max(0, STATUS['waiting'] + delta)
        STATUS['last_seen'] = time.time()


def _schedule_status_refresh():
    try:
        sublime.set_timeout(refresh_status, 0)
        # Remove the activity mark again once it has expired.
        sublime.set_timeout(refresh_status, int(ACTIVITY_SECONDS * 1000) + 100)
    except Exception:
        pass


def status_state(now=None):
    """'off', 'error', 'activity', 'connected' or 'waiting'."""
    now = time.time() if now is None else now
    with STATUS_LOCK:
        if STATUS['error']:
            return 'error'
        if not STATUS['running']:
            return 'off'
        if now - STATUS['activity'] < ACTIVITY_SECONDS:
            return 'activity'
        if STATUS['waiting'] > 0 or now - STATUS['last_seen'] < CLIENT_TIMEOUT_SECONDS:
            return 'connected'
        return 'waiting'


STATUS_TEXT = {
    'error': 'Flexbar ✕',      # bridge could not start (e.g. port in use)
    'activity': 'Flexbar ⇅',   # data was just exchanged with the Flexbar
    'connected': 'Flexbar ●',  # FlexDesigner plugin is connected
    'waiting': 'Flexbar ○',    # bridge loaded, no FlexDesigner plugin connected
}


def status_text(now=None):
    if not sublime.load_settings(SETTINGS_NAME).get('status_indicator', True):
        return None
    return STATUS_TEXT.get(status_state(now))


def _apply_status(view, text):
    if text:
        view.set_status(STATUS_KEY, text)
    else:
        view.erase_status(STATUS_KEY)


def refresh_status(force=False):
    """Update the indicator in every view (main thread). Cheap if nothing changed."""
    try:
        text = status_text()
        with STATUS_LOCK:
            if text == STATUS['shown'] and not force:
                return
            STATUS['shown'] = text
        for window in sublime.windows():
            for view in window.views():
                _apply_status(view, text)
    except Exception:
        pass  # never let the indicator disturb Sublime or the bridge


def _status_tick(generation):
    with STATUS_LOCK:
        if generation != STATUS['generation']:
            return  # plugin was reloaded/unloaded
    refresh_status()
    sublime.set_timeout(lambda: _status_tick(generation), STATUS_TICK_MS)


def _start_status_indicator():
    with STATUS_LOCK:
        STATUS['generation'] += 1
        generation = STATUS['generation']
    refresh_status(force=True)
    sublime.set_timeout(lambda: _status_tick(generation), STATUS_TICK_MS)


def make_handler(expected_token):
    class RequestHandler(BaseHTTPRequestHandler):
        server_version = 'FlexbarBridge/' + VERSION

        def log_message(self, fmt, *args):
            pass  # No HTTP access log, particularly no credentials.

        def send_json(self, status, obj):
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def send_not_modified(self):
            self.send_response(304)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def authenticated(self):
            # No browser-origin CORS support. Access requires private bearer token.
            candidate = self.headers.get('Authorization', '')
            return secrets.compare_digest(candidate, 'Bearer ' + expected_token)

        def do_GET(self):
            if not self.authenticated():
                return self.send_json(403, {'error': 'Forbidden'})
            parts = urlsplit(self.path)
            if parts.path not in ('/v1/state', '/v1/menu'):
                return self.send_json(404, {'error': 'Not found'})
            try:
                if parts.path == '/v1/state':
                    note_client(activity=True)
                    return self.send_json(200, state_on_main_thread(builder=build_state))
                query = parse_qs(parts.query)
                known = (query.get('wait') or [''])[0]
                try:
                    wait = float((query.get('timeout') or ['0'])[0])
                except ValueError:
                    wait = 0.0
                wait = max(0.0, min(wait, MAX_WAIT_SECONDS))
                if re.fullmatch(r'[0-9a-f]{16}', known) and wait > 0:
                    _client_waiting(+1)
                    try:
                        state = wait_for_menu_change(known, wait)
                    finally:
                        _client_waiting(-1)
                    if state is None:
                        note_client()  # still connected, nothing changed
                        return self.send_not_modified()
                else:
                    state = state_on_main_thread(builder=build_menu_state)
                state['longPoll'] = True  # tells the client that ?wait= is supported
                note_client(activity=True)
                self.send_json(200, state)
            except (BrokenPipeError, ConnectionResetError):
                pass  # client gave up while waiting
            except Exception as exc:
                print('FlexbarBridge GET error:', repr(exc))
                try:
                    self.send_json(500, {'error': 'Sublime state unavailable'})
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def do_POST(self):
            if not self.authenticated():
                return self.send_json(403, {'error': 'Forbidden'})
            if self.path != '/v1/action':
                return self.send_json(404, {'error': 'Not found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2048:
                    return self.send_json(400, {'error': 'Invalid body size'})
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                aid = payload.get('id') if isinstance(payload, dict) else None
                if not isinstance(aid, str) or not re.fullmatch(r'[0-9a-f]{24}', aid):
                    return self.send_json(400, {'error': 'Invalid action id'})
                with STATE_LOCK:
                    if aid not in ACTION_LOOKUP:
                        return self.send_json(404, {'error': 'Unknown action; refresh the Flexbar'})
                def perform():
                    try:
                        # Re-check availability on the UI thread right before running,
                        # e.g. a selection-only command after the selection vanished.
                        build_state()
                        execute_action(aid)
                    except Exception as exc:
                        print('FlexbarBridge command error:', repr(exc))
                sublime.set_timeout(perform, 0)
                note_client(action=True)
                self.send_json(202, {'queued': True})
            except (ValueError, UnicodeDecodeError, TypeError):
                self.send_json(400, {'error': 'Invalid JSON'})
    return RequestHandler


def plugin_loaded():
    global SERVER, THREAD
    settings = sublime.load_settings(SETTINGS_NAME)
    if not settings.get('enabled', True):
        return
    token = settings.get('token', '')
    if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{64}', token):
        token = secrets.token_hex(32)
        settings.set('token', token)
        sublime.save_settings(SETTINGS_NAME)
    port = settings.get('port', 17864)
    try:
        port = int(port)
        if not 1024 <= port <= 65535:
            raise ValueError('port out of range')
        if SERVER is not None:
            plugin_unloaded()
        SHUTDOWN.clear()
        SERVER = ThreadingHTTPServer(('127.0.0.1', port), make_handler(token))
        SERVER.daemon_threads = True
        THREAD = threading.Thread(target=SERVER.serve_forever, daemon=True, name='FlexbarBridge')
        THREAD.start()
        # Menu edits in the settings file (or ignored packages) reach the Flexbar at once.
        settings.add_on_change(CHANGE_KEY, settings_changed)
        sublime.load_settings('Preferences.sublime-settings').add_on_change(CHANGE_KEY, settings_changed)
        write_localized_commands()
        print('FlexbarBridge %s: 127.0.0.1:%s ready (local only)' % (VERSION, port))
        with STATUS_LOCK:
            STATUS.update(running=True, error=None, port=port, started=time.time(),
                          last_seen=0.0, activity=0.0, waiting=0)
    except (OSError, ValueError) as exc:
        print('FlexbarBridge could not start:', repr(exc))
        with STATUS_LOCK:
            STATUS.update(running=False, error=repr(exc), port=port)
    _start_status_indicator()


def plugin_unloaded():
    global SERVER, THREAD
    old_server, SERVER = SERVER, None
    THREAD = None
    with STATUS_LOCK:
        STATUS.update(running=False, error=None, generation=STATUS['generation'] + 1)
    refresh_status(force=True)  # removes the indicator
    SHUTDOWN.set()  # release waiting long-poll workers
    bump_menu()
    for name in (SETTINGS_NAME, 'Preferences.sublime-settings'):
        try:
            sublime.load_settings(name).clear_on_change(CHANGE_KEY)
        except Exception:
            pass
    if old_server:
        old_server.shutdown()
        old_server.server_close()


class FlexbarBridgeReloadCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        invalidate_package_cache()
        sublime.status_message(tr('Flexbar: plugin command list will be refreshed'))


_SELECTION_STATE = {}  # view id -> has a non-empty selection


def _selection_flag(view):
    try:
        return any(not region.empty() for region in view.sel())
    except Exception:
        return False


def _show_status_in(view):
    """New or newly focused views get the current indicator as well."""
    try:
        with STATUS_LOCK:
            text = STATUS['shown']
        _apply_status(view, text)
    except Exception:
        pass


def status_report(now=None):
    """Human-readable connection details for the status command."""
    now = time.time() if now is None else now
    state = status_state(now)
    with STATUS_LOCK:
        info = dict(STATUS)
    lines = [tr('Flexbar Bridge %s') % VERSION, '']
    if state == 'error':
        lines += [tr('✕ Bridge konnte nicht starten (Port %s).') % info['port'], info['error'] or '',
                  '', tr('Ist der Port belegt? Anderen "port" in den Flexbar-Einstellungen wählen.')]
    elif state == 'off':
        lines += [tr('Bridge ist deaktiviert ("enabled": false).')]
    else:
        lines.append(tr('Bridge läuft auf 127.0.0.1:%s.') % info['port'])
        if info['last_seen']:
            lines.append(tr('Letzter Kontakt der Flexbar: vor %d s.') % max(0, now - info['last_seen']))
        else:
            lines.append(tr('Seit dem Start hat sich die Flexbar noch nicht gemeldet.'))
        lines.append(tr('Anfragen: %d, ausgeführte Aktionen: %d.') % (info['requests'], info['actions']))
        lines.append('')
        if state in ('connected', 'activity'):
            lines.append(tr('● FlexDesigner-Plugin ist verbunden.'))
        else:
            lines += [tr('○ Kein FlexDesigner-Plugin verbunden.'),
                      tr('FlexDesigner prüfen bzw. Plugin neu starten:'),
                      '  npm run plugin:restart   (im Ordner flex-plugin)']
    return '\n'.join(lines)


class FlexbarBridgeStatusCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        sublime.message_dialog(status_report())


class FlexbarBridgeEventListener(sublime_plugin.EventListener):
    """Tells long-polling Flexbar clients when the menu may have changed.

    Every handler is O(1) and only sets a flag; the (cheap) menu evaluation
    happens in the waiting HTTP worker, and identical results are not sent.
    """

    def on_post_save_async(self, view):
        # Rescan palette files only when a palette file itself was edited.
        if (view.file_name() or '').endswith('.sublime-commands'):
            invalidate_package_cache()
        else:
            bump_menu()  # a save can change the detected syntax

    def on_activated_async(self, view):
        _SELECTION_STATE[view.id()] = _selection_flag(view)
        _show_status_in(view)
        bump_menu()

    def on_load_async(self, view):
        _show_status_in(view)
        bump_menu()

    def on_new_async(self, view):
        _show_status_in(view)
        bump_menu()

    def on_close(self, view):
        _SELECTION_STATE.pop(view.id(), None)
        bump_menu()

    def on_selection_modified_async(self, view):
        # Fires on every cursor move; only a selected <-> empty flip matters.
        flag = _selection_flag(view)
        vid = view.id()
        if _SELECTION_STATE.get(vid) is not flag:
            _SELECTION_STATE[vid] = flag
            bump_menu()


class FlexbarBridgeOpenSettingsCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        window = sublime.active_window()
        if window:
            window.open_file(os.path.join(sublime.packages_path(), 'User', SETTINGS_NAME))


class FlexbarBridgeConfigureMenuCommand(sublime_plugin.WindowCommand):
    """Native Sublime quick panels: choose actions and plugin submenus, order/remove.

    No FlexDesigner config file changes and no backend restart needed.
    """
    def run(self):
        self._show_main()

    def _context(self):
        catalogue = build_state()
        current = configured_entries(catalogue)
        return catalogue, list(current)

    def _save(self, entries):
        settings = sublime.load_settings(SETTINGS_NAME)
        settings.set('menu_items', entries)
        sublime.save_settings(SETTINGS_NAME)
        bump_menu()
        sublime.status_message(tr('Flexbar: Menü gespeichert; wird automatisch aktualisiert'))

    def _show_main(self):
        catalogue, entries = self._context()
        rows = [
            [tr('Fertig'), tr('Auswahl übernehmen und Menü schließen')],
            [tr('+ Funktion hinzufügen'), tr('Befehl aus Sublime oder installiertem Paket')],
            [tr('+ Plugin-Untermenü hinzufügen'), tr('Zum Beispiel SFTP → Upload / Download')],
            [tr('Auf Standard zurücksetzen'), tr('Speichern, Zeilenumbruch, Einrückung, SFTP (falls installiert)')],
        ]
        for i, item in enumerate(entries):
            label = item.get('label', 'Aktion') if item.get('type') == 'action' else item.get('name', 'Plugin')
            rows.append([f'{i + 1}. {tr(label)}',
                         tr('Untermenü' if item.get('type') == 'package' else 'Direkte Funktion')
                         + ' · ' + tr('auswählen zum Verschieben/Entfernen')])

        def selected(index):
            if index < 0 or index == 0:
                return
            if index == 1:
                sublime.set_timeout(lambda: self._add_action(catalogue, entries), 0)
            elif index == 2:
                sublime.set_timeout(lambda: self._add_package(catalogue, entries), 0)
            elif index == 3:
                self._save(default_menu_entries(catalogue))
                sublime.set_timeout(self._show_main, 0)
            else:
                sublime.set_timeout(lambda: self._manage_entry(entries, index - 4), 0)
        self.window.show_quick_panel(rows, selected, placeholder=tr('Flexbar: Menü gestalten'))

    def _add_action(self, catalogue, entries):
        existing = {e.get('id') for e in entries if isinstance(e, dict) and e.get('type') == 'action'}
        actions = [(g['name'], a) for g in catalogue['groups'] for a in g['actions']
                   if a['id'] not in existing]
        rows = [[f'{a["label"]}', f'{group} · {a["command"]}'] for group, a in actions]
        if not actions:
            sublime.status_message(tr('Flexbar: keine weiteren Funktionen gefunden'))
            return sublime.set_timeout(self._show_main, 0)

        def selected(index):
            if index < 0:
                return sublime.set_timeout(self._show_main, 0)
            _, action = actions[index]
            entries.append({'type': 'action', 'id': action['id'], 'label': action['label']})
            self._save(entries)
            sublime.set_timeout(self._show_main, 0)
        self.window.show_quick_panel(rows, selected, placeholder=tr('Funktion suchen und hinzufügen'))

    def _add_package(self, catalogue, entries):
        existing = {e.get('name') for e in entries if isinstance(e, dict) and e.get('type') == 'package'}
        names = [package_name(g['name']) for g in catalogue['groups']
                 if is_package_group(g['name']) and package_name(g['name']) not in existing]
        if not names:
            sublime.status_message(tr('Flexbar: keine weiteren Plugins mit Palette-Befehlen gefunden'))
            return sublime.set_timeout(self._show_main, 0)

        def selected(index):
            if index < 0:
                return sublime.set_timeout(self._show_main, 0)
            entries.append({'type': 'package', 'name': names[index]})
            self._save(entries)
            sublime.set_timeout(self._show_main, 0)
        self.window.show_quick_panel(names, selected, placeholder=tr('Plugin-Untermenü auswählen'))

    def _manage_entry(self, entries, index):
        if index >= len(entries):
            return sublime.set_timeout(self._show_main, 0)
        rows = ['Nach oben verschieben', 'Nach unten verschieben', 'Aus Menü entfernen', 'Zurück']

        def selected(choice):
            if choice == 0 and index > 0:
                entries[index - 1], entries[index] = entries[index], entries[index - 1]
                self._save(entries)
            elif choice == 1 and index < len(entries) - 1:
                entries[index + 1], entries[index] = entries[index], entries[index + 1]
                self._save(entries)
            elif choice == 2:
                entries.pop(index)
                self._save(entries)
            sublime.set_timeout(self._show_main, 0)
        self.window.show_quick_panel(rows, selected, placeholder=tr('Menüeintrag bearbeiten'))

# A visual HTML-sheet menu editor. Minihtml links dispatch Sublime commands;
# search, rename and icon selection use native panels rather than HTML inputs.
_EDITOR_SHEETS = {}
_EDITOR_VIEW = {}  # window id -> submenu index (None means main menu)

def _menu_entries():
    return list(configured_entries(build_state()))

def _save_menu(entries):
    settings = sublime.load_settings(SETTINGS_NAME)
    settings.set('menu_items', entries[:80])
    sublime.save_settings(SETTINGS_NAME)
    bump_menu()
    sublime.status_message(tr('Sublime Text: Flexbar-Menü gespeichert'))

def _editor_link(text, op, index=None, action_id_value=None):
    args = {'op': op}
    if index is not None: args['index'] = index
    if action_id_value is not None: args['action_id'] = action_id_value
    uri = 'subl:flexbar_bridge_menu_editor_action ' + json.dumps(args, ensure_ascii=True, separators=(',', ':'))
    return '<a href="%s">%s</a>' % (html.escape(uri, quote=True), html.escape(text))


def render_menu_editor(entries, submenu_index=None, catalogue=None):
    parts = ["""<html><body id="flexbar-sublime-editor">
    <style>
      body { padding: 22px; color: var(--foreground); background-color: var(--background); }
      h1 { font-size: 24px; margin-bottom: 6px; }
      h2 { font-size: 17px; margin-top: 24px; }
      p { font-size: 13px; }
      .muted { color: var(--foreground); opacity: 0.72; }
      .item { margin: 8px 0; padding: 11px; border: 1px solid var(--foreground); }
      .toolbar { margin: 16px 0; }
      .item a { margin-right: 15px; }
      .kind { font-size: 12px; }
      a { text-decoration: none; }
    </style>
    <h1>Sublime Text</h1>
    <p>""" + tr('Flexbar-Menü bearbeiten · Änderungen werden direkt gespeichert und automatisch übernommen.') + """</p>
    <div class="toolbar">"""]
    parts.append(_editor_link(tr('+ Funktion hinzufügen'), 'add_action'))
    parts.append(' &nbsp; ' + _editor_link(tr('+ Plugin hinzufügen'), 'add_package'))
    parts.append(' &nbsp; ' + _editor_link(tr('Standard wiederherstellen'), 'reset'))
    parts.append(' &nbsp; ' + _editor_link(tr('Aktualisieren'), 'refresh'))
    parts.append('</div><h2>%s</h2>' % html.escape(tr('Hauptmenü (%d Einträge)') % len(entries)))
    if not entries:
        parts.append('<p>' + tr('Noch keine Einträge. Oben eine Funktion oder ein Plugin hinzufügen.') + '</p>')
    by_id = ({a['id']: a for g in catalogue.get('groups', []) for a in g['actions']}
             if catalogue else None)
    for i, item in enumerate(entries):
        is_package = item.get('type') == 'package'
        label = str(item.get('label') or (item.get('name') if is_package else 'Aktion') or 'Aktion')
        detail = (tr('Plugin-Untermenü: ') + str(item.get('name', ''))) if is_package else tr('Direkte Funktion')
        if by_id is not None and not is_package:
            found = by_id.get(item.get('id'))
            if found is None or not found.get('enabled', True):
                detail += ' · ' + tr('derzeit nicht verfügbar (Taste bleibt grau)')
        icon = (tr('Nur Text') if item.get('icon') == '__text__' else item.get('icon') or tr('Automatisch'))
        parts.append('<div class="item"><p><b>%s. %s</b> &nbsp; <span class="kind">%s</span></p>' %
                     (i+1, html.escape(label), html.escape(detail)))
        parts.append('<p class="muted">%s</p>' % html.escape(tr('Symbol: ') + icon))
        for text, op in [('↑ Hoch','up'),('↓ Runter','down'),('Name','rename'),
                         ('Symbol','icon'),('Entfernen','remove')]:
            parts.append(_editor_link(tr(text), op, i) + ' &nbsp; ')
        if is_package:
            parts.append(_editor_link(tr('Untermenü bearbeiten'), 'open_package', i))
        parts.append('</div>')
    parts.append('<p>' + tr('Reihenfolge der Einträge = Reihenfolge auf der Flexbar. Ein Plugin öffnet ein Untermenü. Die sechs festen Aktionsplätze bleiben erhalten.') + '</p>')
    parts.append('<p>' + tr('Symbole werden als Material-Design-Icons gezeichnet, nicht als Emoji.') + '</p></body></html>')
    return ''.join(parts)


def render_submenu_editor(entries, index, catalogue):
    """Minihtml sheet: links, not HTML inputs (Sublime minihtml has no forms)."""
    if not 0 <= index < len(entries) or entries[index].get('type') != 'package':
        return render_menu_editor(entries)
    entry = entries[index]
    groups = catalogue.get('groups', [])
    group = next((g for g in groups if g['name'] == package_group(str(entry.get('name')))), None)
    if group is None:
        return ('<html><body><h2>' + tr('Plugin nicht verfügbar') + '</h2><p>' +
                _editor_link(tr('Zurück zum Hauptmenü'), 'back') + '</p></body></html>')
    actions = group['actions']
    enabled = submenu_selected_ids(entry, actions)
    title = html.escape(str(entry.get('label') or entry.get('name') or 'Plugin'))
    parts = ['''<html><body id="flexbar-sublime-submenu"><style>
        body { padding:22px; color:var(--foreground); background-color:var(--background); }
        h1 {font-size:24px; margin-bottom:8px;} p {font-size:13px;}
        .toolbar {margin: 15px 0; padding:10px; border:1px solid var(--foreground);}
        .row {margin:6px 0; padding:11px; border:1px solid var(--foreground);}
        .muted {opacity:0.7;} a {text-decoration:none;}
      </style>''', '<h1>' + title + '</h1>',
        '<p>' + _editor_link(tr('‹ Zurück zum Hauptmenü'), 'back') + '</p>',
        '<p><b>%s</b></p>' % (html.escape(tr('%d von %d Funktionen ausgewählt') % (len(enabled), len(actions))))]
    parts.append('<div class="toolbar"><p><b>' + tr('Funktionen anzeigen') + '</b></p>')
    parts.append(_editor_link(tr('Alle abwählen'), 'all_off', index))
    parts.append(' &nbsp; | &nbsp; ' + _editor_link(tr('Alle auswählen'), 'all_on', index))
    parts.append('<p><b>' + tr('Symbole im Untermenü') + '</b></p>')
    parts.append(_editor_link(tr('Alle Symbole ausblenden'), 'icons_all_off', index))
    parts.append(' &nbsp; | &nbsp; ' + _editor_link(tr('Alle Symbole anzeigen'), 'icons_all_on', index))
    parts.append('</div>')
    parts.append('<p class="muted">' + tr('[x] schaltet die Funktion ein oder aus. Mit „Symbol wählen“ legst du für jede Funktion ein eigenes Icon fest (auch wenn kein automatisches Icon bekannt ist). „Alle Symbole ausblenden“ betrifft nur die Anzeige, nicht deine Auswahl.') + '</p>')
    for action in actions:
        aid = action['id']
        selected = aid in enabled
        icon = submenu_icon(entry, action)
        override = submenu_icon_override(entry, aid)
        if override == '__text__':
            icon_info = tr('Nur Text (manuell)')
        elif override in KNOWN_ICONS:
            icon_info = tr('Manuell: ') + tr(ICON_LABELS.get(override, override))
        elif action.get('icon') in KNOWN_ICONS:
            icon_info = tr('Automatisch: ') + tr(ICON_LABELS.get(action['icon'], action['icon']))
        else:
            icon_info = tr('Automatisch: kein Symbol verfügbar')
        display = tr('Symbol wird angezeigt' if icon else 'Text wird angezeigt')
        parts.append('<div class="row"><p><b>' + _editor_link('[x]' if selected else '[ ]',
                     'toggle_action', index, aid) + ' &nbsp; ' + html.escape(action['label']) + '</b></p>')
        parts.append('<p class="muted">' + html.escape(icon_info) + ' · ' + display + '</p>')
        parts.append('<p>' + _editor_link(tr('Symbol wählen'), 'choose_action_icon', index, aid))
        if (action.get('icon') in KNOWN_ICONS or override in KNOWN_ICONS) and override != '__text__':
            parts.append(' &nbsp; | &nbsp; ' + _editor_link(tr('Symbol ausblenden' if icon else 'Symbol anzeigen'),
                         'toggle_action_icon', index, aid))
        parts.append('</p></div>')
    parts.append('<p>' + _editor_link(tr('‹ Zurück zum Hauptmenü'), 'back') + '</p></body></html>')
    return ''.join(parts)


class FlexbarBridgeMenuEditorCommand(sublime_plugin.WindowCommand):
    def run(self):
        key = self.window.id()
        sheet = _EDITOR_SHEETS.get(key)
        catalogue = build_state()
        entries = list(configured_entries(catalogue))
        view = _EDITOR_VIEW.get(key)
        content = (render_submenu_editor(entries, view, catalogue)
                   if isinstance(view, int) else render_menu_editor(entries, catalogue=catalogue))
        if sheet and sheet.window() == self.window:
            sheet.set_contents(content)
            self.window.focus_sheet(sheet)
        else:
            _EDITOR_SHEETS[key] = self.window.new_html_sheet(
                tr('Sublime Text · Flexbar-Menü'), content)


class FlexbarBridgeMenuEditorActionCommand(sublime_plugin.WindowCommand):
    def _reload(self):
        self.window.run_command('flexbar_bridge_menu_editor')

    def _save(self, entries):
        _save_menu(entries)
        self._reload()

    def run(self, op='', index=None, action_id=None):
        entries = _menu_entries()
        if op == 'refresh':
            return self._reload()
        if op == 'back':
            _EDITOR_VIEW.pop(self.window.id(), None)
            return self._reload()
        if op == 'open_package':
            if isinstance(index, int) and 0 <= index < len(entries) and entries[index].get('type') == 'package':
                _EDITOR_VIEW[self.window.id()] = index
                return self._reload()
            return
        if op == 'reset':
            if sublime.ok_cancel_dialog(tr('Sublime Text: Die Menükonfiguration auf die Standardauswahl zurücksetzen?')):
                _EDITOR_VIEW.pop(self.window.id(), None)
                return self._save(default_menu_entries(build_state()))
            return
        if op == 'add_action':
            catalogue = build_state()
            existing = {i.get('id') for i in entries if i.get('type') == 'action'}
            actions = [(g['name'], a) for g in catalogue['groups'] for a in g['actions']
                       if a['id'] not in existing]
            rows = [[a['label'], group + ' · ' + a['command']] for group, a in actions]
            def done(pos):
                if pos < 0: return self._reload()
                group, a = actions[pos]
                entries.append({'type':'action', 'id':a['id'], 'label':a['label']})
                self._save(entries)
            if not rows: return sublime.status_message(tr('Keine zusätzlichen Funktionen verfügbar'))
            return self.window.show_quick_panel(rows, done, placeholder=tr('Funktion suchen…'))
        if op == 'add_package':
            groups = build_state()['groups']
            existing = {i.get('name') for i in entries if i.get('type') == 'package'}
            names = [package_name(g['name']) for g in groups if is_package_group(g['name'])
                     and package_name(g['name']) not in existing]
            def done(pos):
                if pos < 0: return self._reload()
                entries.append({'type':'package','name':names[pos]})
                self._save(entries)
            if not names: return sublime.status_message(tr('Keine zusätzlichen Plugins verfügbar'))
            return self.window.show_quick_panel(names, done, placeholder=tr('Plugin suchen…'))
        if not isinstance(index, int) or not 0 <= index < len(entries): return
        item = entries[index]
        if op == 'up' and index > 0:
            entries[index-1],entries[index] = entries[index],entries[index-1]
            return self._save(entries)
        if op == 'down' and index < len(entries)-1:
            entries[index+1],entries[index] = entries[index],entries[index+1]
            return self._save(entries)
        if op == 'remove':
            entries.pop(index)
            return self._save(entries)
        if op == 'rename':
            old = item.get('label') or item.get('name') or ''
            def done(value):
                value = value.strip()[:54]
                if value:
                    item['label'] = value
                    self._save(entries)
            return self.window.show_input_panel(tr('Tastenbeschriftung'), old, done, None, None)
        if op == 'icon':
            rows = icon_picker_rows(item.get('icon'))
            def done(pos):
                if pos < 0: return self._reload()
                icon = ICONS[pos][1]
                if icon: item['icon'] = icon
                else: item.pop('icon', None)
                self._save(entries)
                icon_hint(icon)
            return self.window.show_quick_panel(rows, done, placeholder=tr('Symbol suchen, z. B. Umbenennen, Einstellungen, Git…'))
        if op == 'package_actions' and item.get('type') == 'package':
            # Backwards compatibility with older editor links.
            _EDITOR_VIEW[self.window.id()] = index
            return self._reload()
        if item.get('type') != 'package':
            return
        if op not in ('all_off', 'all_on', 'toggle_action',
                      'icons_all_off', 'icons_all_on', 'toggle_action_icon',
                      'choose_action_icon'):
            return
        groups = build_state()['groups']
        group = next((g for g in groups if g['name'] == package_group(str(item.get('name')))), None)
        if group is None:
            return sublime.status_message(tr('Das Plugin ist nicht verfügbar'))
        actions = group['actions']
        available = {a['id'] for a in actions}
        if op == 'choose_action_icon':
            if not isinstance(action_id, str) or action_id not in available:
                return
            choice = submenu_icon_override(item, action_id)
            rows = icon_picker_rows(choice)
            def done(pos):
                if pos < 0:
                    return self._reload()
                set_submenu_icon(item, action_id, ICONS[pos][1])
                self._save(entries)
                icon_hint(ICONS[pos][1])
            return self.window.show_quick_panel(rows, done,
                placeholder=tr('Symbol suchen, z. B. Zahnrad, Umbenennen, Upload…'))
        if op == 'all_off':
            item['action_ids'] = []
        elif op == 'all_on':
            # No filter also includes commands installed in this package later.
            item.pop('action_ids', None)
        elif op == 'toggle_action':
            if not isinstance(action_id, str) or action_id not in available:
                return
            selected = submenu_selected_ids(item, actions)
            if action_id in selected:
                selected.remove(action_id)
            else:
                selected.add(action_id)
            item['action_ids'] = [a['id'] for a in actions if a['id'] in selected]
        elif op == 'icons_all_off':
            item['sub_icons'] = 'text'
            item.pop('icon_toggle_ids', None)
        elif op == 'icons_all_on':
            item.pop('sub_icons', None)
            item.pop('icon_toggle_ids', None)
        elif op == 'toggle_action_icon':
            if not isinstance(action_id, str) or action_id not in available:
                return
            # Flip this one command relative to the submenu-wide default.
            saved = item.get('icon_toggle_ids', [])
            toggles = {x for x in saved if isinstance(x, str)} if isinstance(saved, list) else set()
            if action_id in toggles: toggles.remove(action_id)
            else: toggles.add(action_id)
            item['icon_toggle_ids'] = [a['id'] for a in actions if a['id'] in toggles]
        return self._save(entries)
