"""Tests for the Sublime bridge, outside Sublime Text."""
import importlib.util
import json
import os
import secrets
import sys
import threading
import time
import types
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(__file__))
FILE = os.path.join(ROOT, 'FlexbarBridge', 'flexbar_bridge.py')

class FakeSettings:
    def __init__(self, data=None): self.data=dict(data or {})
    def get(self, name, default=None): return self.data.get(name, default)
    def set(self, name, value): self.data[name]=value
class FakeView:
    def settings(self): return FakeSettings({'syntax':'Packages/Python/Python.sublime-syntax'})
    def sel(self): return [types.SimpleNamespace(empty=lambda: False)]
    def is_dirty(self): return True
class NoSelectionView(FakeView):
    def sel(self): return [types.SimpleNamespace(empty=lambda: True)]
class FakeSheet:
    def __init__(self, window, name, contents):
        self.host=window; self.name=name; self.contents=contents
    def window(self): return self.host
    def set_contents(self, text): self.contents=text

class FakeWindow:
    def __init__(self):
        self.calls=[]; self.panel=None; self.sheet=None; self.input_panel=None
        self.view_factory=FakeView
    def id(self): return 123
    def new_html_sheet(self, name, contents):
        self.sheet=FakeSheet(self,name,contents); return self.sheet
    def focus_sheet(self,sheet): self.sheet=sheet
    def show_input_panel(self,label,value,done,changed,cancel):
        self.input_panel=(label,value,done); return None
    def active_view(self): return self.view_factory()
    def run_command(self, name, args=None):
        self.calls.append((name, args))
        if name == 'flexbar_bridge_menu_editor':
            cmd=BridgeTests.module.FlexbarBridgeMenuEditorCommand()
            cmd.window=self
            cmd.run()
    def show_quick_panel(self, rows, callback, **kw): self.panel=(rows, callback)

class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sublime=types.ModuleType('sublime')
        sublime.settings={
            'FlexbarBridge.sublime-settings':FakeSettings({'custom_commands':[{'label':'Probe','command':'probe','group':'Extra'}]}),
            'Preferences.sublime-settings':FakeSettings({'ignored_packages':['HiddenPlugin']})
        }
        sublime.load_settings=lambda name:sublime.settings[name]
        sublime.find_resources=lambda pattern:[
            'Packages/SFTP/Default.sublime-commands',
            'Packages/GitSavvy/Default.sublime-commands',
            'Packages/HiddenPlugin/Default.sublime-commands',
            'Packages/Default/Default.sublime-commands']
        def load_resource(p, **kw):
            if '/SFTP/' in p:
                return json.dumps([{'caption':'SFTP: Upload','command':'sftp_upload'},
                                   {'caption':'SFTP: Download','command':'sftp_download'}])
            return '[{"caption":"Git status","command":"gs_status"}]'
        sublime.load_resource=load_resource
        sublime.decode_value=json.loads
        sublime.active_window=lambda:cls.window
        sublime.set_timeout=lambda cb,delay=0:cb()
        sublime.save_settings=lambda name:None
        sublime.status_message=lambda msg:None
        sublime.packages_path=lambda:'/tmp/Packages'
        sublime.ok_cancel_dialog=lambda message:True
        sublime_plugin=types.ModuleType('sublime_plugin')
        sublime_plugin.ApplicationCommand=type('ApplicationCommand',(),{})
        sublime_plugin.WindowCommand=type('WindowCommand',(),{})
        sublime_plugin.EventListener=type('EventListener',(),{})
        sys.modules['sublime']=sublime
        sys.modules['sublime_plugin']=sublime_plugin
        cls.sublime=sublime
        cls.window=FakeWindow()
        spec=importlib.util.spec_from_file_location('bridge_under_test', FILE)
        cls.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self):
        self.sublime.settings['FlexbarBridge.sublime-settings'].data.pop('menu_items',None)
        self.module._EDITOR_VIEW.clear()
        self.sublime.settings['FlexbarBridge.sublime-settings'].data.pop('blocked_icons',None)
        self.window.view_factory=FakeView

    def test_default_menu_only_selected_and_sftp(self):
        result=self.module.build_menu_state()
        names=[i['label'] for i in result['items']]
        self.assertIn('Zeilenumbruch',names)
        self.assertIn('Einrückung',names)
        self.assertIn('SFTP',names)
        self.assertNotIn('GitSavvy',names)
        sftp=next(i for i in result['items'] if i['label']=='SFTP')
        self.assertEqual(sftp['type'],'menu')
        self.assertEqual([x['label'] for x in sftp['items']],['Upload','Download'])
        self.assertEqual(len(result['items']),4)

    def test_selection_persists_and_filters(self):
        self.sublime.settings['FlexbarBridge.sublime-settings'].set('menu_items',[
            {'type':'package','name':'GitSavvy'}])
        result=self.module.build_menu_state()
        self.assertEqual([i['label'] for i in result['items']],['GitSavvy'])
        self.assertEqual(result['items'][0]['items'][0]['label'],'Git status')

    def test_picker_adds_package_and_preserves_other_settings(self):
        cls=self.module.FlexbarBridgeConfigureMenuCommand
        cmd=cls();cmd.window=self.window
        self.sublime.settings['FlexbarBridge.sublime-settings'].set('menu_items',[])
        cmd.run()
        self.window.panel[1](2)  # Add plugin
        rows,select=self.window.panel
        self.assertIn('SFTP',rows)
        select(rows.index('SFTP'))
        setting=self.sublime.settings['FlexbarBridge.sublime-settings']
        self.assertEqual(setting.get('menu_items')[-1],{'type':'package','name':'SFTP'})
        self.assertEqual(setting.get('custom_commands')[0]['command'],'probe')

    def test_icons_for_core_and_sftp_commands(self):
        menu=self.module.build_menu_state()['items']
        save=next(i for i in menu if i['label']=='Speichern')
        wrap=next(i for i in menu if i['label']=='Zeilenumbruch')
        sftp=next(i for i in menu if i['label']=='SFTP')
        self.assertEqual(save['icon'],'mdi mdi-content-save')
        self.assertEqual(wrap['icon'],'mdi mdi-keyboard-return')
        self.assertEqual(sftp['icon'],'mdi mdi-cloud-outline')
        self.assertEqual(sftp['items'][0]['icon'],'mdi mdi-cloud-upload')

    def test_visual_editor_renders_and_can_reorder_rename_and_set_icon(self):
        catalogue=self.module.build_state()
        original=self.module.default_menu_entries(catalogue)
        self.sublime.settings['FlexbarBridge.sublime-settings'].set('menu_items',original)
        window=self.window
        cmd=self.module.FlexbarBridgeMenuEditorCommand()
        cmd.window=window
        cmd.run()
        self.assertIn('Sublime Text',window.sheet.contents)
        self.assertIn('subl:flexbar_bridge_menu_editor_action',window.sheet.contents)
        self.assertIn('Speichern',window.sheet.contents)
        editor=self.module.FlexbarBridgeMenuEditorActionCommand()
        editor.window=window
        editor.run(op='down',index=0)
        self.assertEqual(self.sublime.settings['FlexbarBridge.sublime-settings'].get('menu_items')[1]['label'],'Speichern')
        editor.run(op='rename',index=1)
        window.input_panel[2]('Jetzt sichern')
        self.assertIn('Jetzt sichern',window.sheet.contents)
        editor.run(op='icon',index=1)
        options, callback = window.panel
        callback(next(i for i,x in enumerate(options) if 'Diskette' in x))
        menu=self.module.build_menu_state()['items']
        edited=next(i for i in menu if i['label']=='Jetzt sichern')
        self.assertEqual(edited['icon'],'mdi mdi-content-save')

    def test_submenu_command_selection_is_saved_and_enforced(self):
        settings=self.sublime.settings['FlexbarBridge.sublime-settings']
        settings.set('menu_items', [{'type':'package','name':'SFTP'}])
        editor=self.module.FlexbarBridgeMenuEditorActionCommand()
        editor.window=self.window
        editor.run(op='open_package',index=0)
        self.assertIn('Alle abwählen', self.window.sheet.contents)
        self.assertIn('Alle auswählen', self.window.sheet.contents)
        self.assertIn('2 von 2 Funktionen ausgewählt', self.window.sheet.contents)
        actions=next(g['actions'] for g in self.module.build_state()['groups']
                     if g['name']=='Paket: SFTP')
        editor.run(op='all_off',index=0)
        self.assertEqual(settings.get('menu_items')[0]['action_ids'], [])
        self.assertEqual(self.module.build_menu_state()['items'], [])
        self.assertIn('0 von 2 Funktionen ausgewählt', self.window.sheet.contents)
        editor.run(op='toggle_action',index=0, action_id=actions[1]['id'])
        state=self.module.build_menu_state()['items']
        self.assertEqual([a['label'] for a in state[0]['items']], ['Download'])
        editor.run(op='toggle_action',index=0, action_id=actions[0]['id'])
        self.assertEqual([a['label'] for a in self.module.build_menu_state()['items'][0]['items']],
                         ['Upload','Download'])
        editor.run(op='toggle_action',index=0, action_id=actions[1]['id'])
        self.assertEqual([a['label'] for a in self.module.build_menu_state()['items'][0]['items']],
                         ['Upload'])
        editor.run(op='all_on',index=0)
        self.assertNotIn('action_ids', settings.get('menu_items')[0])
        editor.run(op='back')
        self.assertIn('Hauptmenü',self.window.sheet.contents)

    def test_submenu_icon_visibility_independent_of_selection(self):
        settings=self.sublime.settings['FlexbarBridge.sublime-settings']
        settings.set('menu_items', [{'type':'package','name':'SFTP'}])
        editor=self.module.FlexbarBridgeMenuEditorActionCommand()
        editor.window=self.window
        actions=next(g['actions'] for g in self.module.build_state()['groups']
                     if g['name']=='Paket: SFTP')
        upload_id,download_id=[a['id'] for a in actions]
        editor.run(op='open_package',index=0)
        self.assertIn('Alle Symbole ausblenden', self.window.sheet.contents)
        editor.run(op='icons_all_off',index=0)
        shown=self.module.build_menu_state()['items'][0]['items']
        self.assertEqual([i['icon'] for i in shown],[None,None])
        editor.run(op='toggle_action_icon',index=0,action_id=upload_id)
        shown=self.module.build_menu_state()['items'][0]['items']
        self.assertEqual(shown[0]['icon'],'mdi mdi-cloud-upload')
        self.assertIsNone(shown[1]['icon'])
        editor.run(op='toggle_action_icon',index=0,action_id=upload_id)
        self.assertIsNone(self.module.build_menu_state()['items'][0]['items'][0]['icon'])
        editor.run(op='icons_all_on',index=0)
        shown=self.module.build_menu_state()['items'][0]['items']
        self.assertEqual(shown[0]['icon'],'mdi mdi-cloud-upload')
        self.assertEqual(shown[1]['icon'],'mdi mdi-cloud-download')
        editor.run(op='toggle_action_icon',index=0,action_id=download_id)
        shown=self.module.build_menu_state()['items'][0]['items']
        self.assertIsNotNone(shown[0]['icon'])
        self.assertIsNone(shown[1]['icon'])
        self.assertNotIn('action_ids',settings.get('menu_items')[0])

    def test_manual_icon_picker_per_submenu_command_and_visibility(self):
        settings=self.sublime.settings['FlexbarBridge.sublime-settings']
        settings.set('menu_items', [{'type':'package','name':'SFTP'}])
        editor=self.module.FlexbarBridgeMenuEditorActionCommand()
        editor.window=self.window
        actions=next(g['actions'] for g in self.module.build_state()['groups']
                     if g['name']=='Paket: SFTP')
        upload_id, download_id = [a['id'] for a in actions]
        editor.run(op='open_package', index=0)
        self.assertIn('Symbol wählen', self.window.sheet.contents)

        # Manual icon selection changes only the chosen action.
        editor.run(op='choose_action_icon', index=0, action_id=download_id)
        rows, picked = self.window.panel
        self.assertIn('Automatisch', rows[0])
        self.assertIn('Nur Text', rows[1])
        picked(next(i for i, x in enumerate(rows) if 'Diskette' in x))
        submenu=self.module.build_menu_state()['items'][0]['items']
        self.assertEqual(submenu[0]['icon'], 'mdi mdi-cloud-upload')
        self.assertEqual(submenu[1]['icon'], 'mdi mdi-content-save')
        self.assertEqual(settings.get('menu_items')[0]['sub_icon_overrides'],
                         {download_id: 'mdi mdi-content-save'})
        self.assertIn('Manuell: Diskette', self.window.sheet.contents)

        # Global icon hiding preserves manual icon choices.
        editor.run(op='icons_all_off', index=0)
        self.assertEqual([a['icon'] for a in self.module.build_menu_state()['items'][0]['items']], [None, None])
        self.assertEqual(settings.get('menu_items')[0]['sub_icon_overrides'][download_id],
                         'mdi mdi-content-save')
        editor.run(op='choose_action_icon', index=0, action_id=download_id)
        rows, picked = self.window.panel
        picked(next(i for i, x in enumerate(rows) if 'Diskette' in x))
        submenu=self.module.build_menu_state()['items'][0]['items']
        self.assertIsNone(submenu[0]['icon'])
        self.assertEqual(submenu[1]['icon'], 'mdi mdi-content-save')

        # Text-only choice supersedes even a visible manually assigned icon.
        editor.run(op='choose_action_icon', index=0, action_id=download_id)
        self.window.panel[1](1)  # Nur Text
        self.assertIsNone(self.module.build_menu_state()['items'][0]['items'][1]['icon'])
        editor.run(op='icons_all_on', index=0)
        self.assertIsNone(self.module.build_menu_state()['items'][0]['items'][1]['icon'])

        # Automatic clears override and restores SFTP's suggested icon.
        editor.run(op='choose_action_icon', index=0, action_id=download_id)
        self.window.panel[1](0)  # Automatisch
        self.assertEqual(self.module.build_menu_state()['items'][0]['items'][1]['icon'],
                         'mdi mdi-cloud-download')
        self.assertNotIn('sub_icon_overrides', settings.get('menu_items')[0])

    def test_manual_icon_assignment_even_without_auto_icon(self):
        # A package command without automatic mapping can still use a chosen icon.
        action={'id':'abc123', 'icon':None, 'label':'Unknown command'}
        entry={'type':'package', 'name':'Example'}
        self.assertIsNone(self.module.submenu_icon(entry, action))
        self.module.set_submenu_icon(entry, action['id'], 'mdi mdi-source-branch')
        self.assertEqual(self.module.submenu_icon(entry, action), 'mdi mdi-source-branch')
        self.module.set_submenu_icon(entry, action['id'], '__text__')
        self.assertIsNone(self.module.submenu_icon(entry, action))
        self.module.set_submenu_icon(entry, action['id'], None)
        self.assertNotIn('sub_icon_overrides', entry)

    def test_invalid_manual_icon_choice_does_not_change_configuration(self):
        settings=self.sublime.settings['FlexbarBridge.sublime-settings']
        settings.set('menu_items', [{'type':'package','name':'SFTP'}])
        editor=self.module.FlexbarBridgeMenuEditorActionCommand()
        editor.window=self.window
        self.window.panel = None
        editor.run(op='choose_action_icon', index=0, action_id='0'*24)
        self.assertIsNone(self.window.panel)
        self.assertNotIn('sub_icon_overrides', settings.get('menu_items')[0])

    def test_invalid_submenu_action_id_does_not_change_selection(self):
        settings=self.sublime.settings['FlexbarBridge.sublime-settings']
        settings.set('menu_items', [{'type':'package','name':'SFTP'}])
        editor=self.module.FlexbarBridgeMenuEditorActionCommand()
        editor.window=self.window
        editor.run(op='toggle_action',index=0,action_id='0'*24)
        self.assertEqual(settings.get('menu_items'),[{'type':'package','name':'SFTP'}])

    def test_only_text_choice_and_unknown_actions_have_no_icon(self):
        self.assertIsNone(self.module.suggested_icon('custom_task', {}, 'Unbekannt', 'Custom'))
        settings=self.sublime.settings['FlexbarBridge.sublime-settings']
        catalogue=self.module.build_state()
        action=next(a for g in catalogue['groups'] for a in g['actions'] if a['command']=='save')
        settings.set('menu_items',[{'type':'action','id':action['id'],
                                    'label':'Speichern ohne Icon','icon':'__text__'}])
        shown=self.module.build_menu_state()['items']
        self.assertEqual(len(shown),1)
        self.assertIsNone(shown[0]['icon'])
        self.assertEqual(shown[0]['label'],'Speichern ohne Icon')

    def test_extended_icon_catalogue_is_searchable_and_unique(self):
        icons=self.module.ICONS
        self.assertIsNone(icons[0][1])
        self.assertEqual(icons[1][1], '__text__')
        self.assertGreaterEqual(len(icons), 160)
        self.assertEqual(len(set(value for _, value in icons)),len(icons))
        self.assertEqual(len(self.module.KNOWN_ICONS),len(icons)-2)
        values=dict(icons)
        self.assertEqual(values['Allgemein · Einstellungen / Zahnrad'], 'mdi mdi-cog')
        self.assertEqual(values['Dateien & Ordner · Datei umbenennen'], 'mdi mdi-rename-box')
        self.assertEqual(values['Bearbeiten & Text · Umbenennen'], 'mdi mdi-rename')
        self.assertEqual(values['Allgemein · Löschen / Papierkorb'], 'mdi mdi-delete-outline')
        self.assertEqual(values['Git & Versionierung · Git-Logo'], 'mdi mdi-git')
        for label, code in icons[2:]:
            self.assertTrue(label)
            self.assertRegex(code, r'^mdi mdi-[a-z0-9-]+$')

    def test_extended_icons_main_menu_and_submenu(self):
        settings=self.sublime.settings['FlexbarBridge.sublime-settings']
        save=next(a for g in self.module.build_state()['groups'] for a in g['actions']
                  if a['origin']=='core' and a['command']=='save')
        settings.set('menu_items', [{'type':'action','id':save['id'], 'label':'Speichern'}])
        editor=self.module.FlexbarBridgeMenuEditorActionCommand()
        editor.window=self.window
        editor.run(op='icon',index=0)
        options, choose=self.window.panel
        selected=next(i for i,x in enumerate(options) if 'Einstellungen / Zahnrad' in x)
        choose(selected)
        self.assertEqual(self.module.build_menu_state()['items'][0]['icon'],'mdi mdi-cog')

        settings.set('menu_items', [{'type':'package','name':'SFTP'}])
        actions=next(g['actions'] for g in self.module.build_state()['groups']
                     if g['name']=='Paket: SFTP')
        editor.run(op='choose_action_icon',index=0,action_id=actions[0]['id'])
        options,choose=self.window.panel
        chosen=next(i for i,x in enumerate(options) if 'Datei umbenennen' in x)
        choose(chosen)
        self.assertEqual(self.module.build_menu_state()['items'][0]['items'][0]['icon'], 'mdi mdi-rename-box')
        self.assertEqual(self.module.build_menu_state()['items'][0]['items'][1]['icon'], 'mdi mdi-cloud-download')

    def test_automatic_icon_recognition_rename_and_settings(self):
        self.assertEqual(self.module.suggested_icon('rename_file', {}, 'Umbenennen', 'SFTP'),
                         'mdi mdi-rename-box')
        self.assertEqual(self.module.suggested_icon('sftp_settings', {}, 'SFTP: Preferences', 'SFTP'),
                         'mdi mdi-cog')
        self.assertEqual(self.module.suggested_icon('configure', {}, 'Einstellungen', 'Other'),
                         'mdi mdi-cog')

    def test_api_menu_and_action_authorized(self):
        state=self.module.build_menu_state()
        action=state['items'][0]
        token=secrets.token_hex(32)
        server=self.module.ThreadingHTTPServer(('127.0.0.1',0),self.module.make_handler(token))
        server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:%d'%server.server_port
        try:
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(url+'/v1/menu',timeout=1)
            self.assertEqual(err.exception.code,403)
            headers={'Authorization':'Bearer '+token}
            state=json.load(urllib.request.urlopen(urllib.request.Request(url+'/v1/menu',headers=headers),timeout=2))
            self.assertEqual(state['schema'],3)
            self.assertEqual(len(state['items']),4)
            request=urllib.request.Request(url+'/v1/action',
                data=json.dumps({'id':action['id']}).encode(),
                headers={**headers,'Content-Type':'application/json'},method='POST')
            self.assertTrue(json.load(urllib.request.urlopen(request,timeout=2))['queued'])
            self.assertTrue(any(name=='save' for name, _ in self.window.calls))
        finally:
            server.shutdown();server.server_close()

    # ------------------------------------------------------------ 1.0.0
    def _core_action(self, command):
        return next(a for g in self.module.build_state()['groups'] for a in g['actions']
                    if a['origin'] == 'core' and a['command'] == command)

    def _context_action(self, label):
        group = next(g for g in self.module.build_state()['groups'] if g['name'].startswith('Kontext'))
        return next(a for a in group['actions'] if a['label'] == label)

    def _start_server(self):
        token = secrets.token_hex(32)
        server = self.module.ThreadingHTTPServer(('127.0.0.1', 0), self.module.make_handler(token))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        def stop():
            server.shutdown(); server.server_close()
        self.addCleanup(stop)
        url = 'http://127.0.0.1:%d' % server.server_port
        headers = {'Authorization': 'Bearer ' + token}
        def get(path, timeout=5):
            request = urllib.request.Request(url + path, headers=headers)
            return json.load(urllib.request.urlopen(request, timeout=timeout))
        return get, url, headers

    def test_version_is_exposed_in_documentation(self):
        version = self.module.VERSION
        with open(os.path.join(ROOT, 'README.md'), encoding='utf-8') as handle:
            self.assertIn(version, handle.readline())

    def test_default_core_labels_use_proper_umlauts(self):
        labels = [label for _, items in self.module.CORE for label, _, _ in items]
        for expected in ('Rückgängig', 'Datei öffnen', 'Einrücken', 'Ausrücken',
                         'Nächster Treffer', 'Nächster Tab', 'Einfügen'):
            self.assertIn(expected, labels)
        for ascii_label in ('Rueckgaengig', 'Datei oeffnen', 'Naechster Tab', 'Einfuegen'):
            self.assertNotIn(ascii_label, labels)

    def test_menu_version_is_stable_and_changes_with_the_menu(self):
        get, _, _ = self._start_server()
        first, second = get('/v1/menu'), get('/v1/menu')
        self.assertRegex(first['version'], r'^[0-9a-f]{16}$')
        self.assertEqual(first['version'], second['version'])
        self.assertTrue(first['longPoll'])
        self.sublime.settings['FlexbarBridge.sublime-settings'].set('menu_items', [])
        self.assertNotEqual(get('/v1/menu')['version'], first['version'])

    def test_long_poll_answers_304_when_nothing_changes(self):
        get, _, _ = self._start_server()
        version = get('/v1/menu')['version']
        started = time.monotonic()
        with self.assertRaises(urllib.error.HTTPError) as err:
            get('/v1/menu?wait=%s&timeout=0.4' % version)
        self.assertEqual(err.exception.code, 304)
        self.assertGreaterEqual(time.monotonic() - started, 0.3)

    def test_long_poll_returns_as_soon_as_the_menu_changes(self):
        get, _, _ = self._start_server()
        version = get('/v1/menu')['version']
        settings = self.sublime.settings['FlexbarBridge.sublime-settings']
        def change():
            time.sleep(0.3)
            settings.set('menu_items', [])
            self.module.bump_menu()
        threading.Thread(target=change, daemon=True).start()
        started = time.monotonic()
        state = get('/v1/menu?wait=%s&timeout=10' % version)
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.2)
        self.assertLess(elapsed, 3)
        self.assertNotEqual(state['version'], version)
        self.assertEqual(state['items'], [])

    def test_long_poll_is_released_on_shutdown(self):
        get, _, _ = self._start_server()
        version = get('/v1/menu')['version']
        self.addCleanup(self.module.SHUTDOWN.clear)
        def stop():
            self.module.SHUTDOWN.set()
            self.module.bump_menu()
        threading.Timer(0.2, stop).start()
        started = time.monotonic()
        with self.assertRaises(urllib.error.HTTPError) as err:
            get('/v1/menu?wait=%s&timeout=20' % version)
        self.assertEqual(err.exception.code, 304)
        self.assertLess(time.monotonic() - started, 3)

    def test_wait_parameters_are_validated(self):
        get, _, _ = self._start_server()
        # Garbage versions or timeouts never block: the current state is returned at once.
        for query in ('wait=zzz&timeout=10', 'wait=%s&timeout=abc' % ('a' * 16), 'timeout=5', 'wait=%s' % ('a' * 16)):
            started = time.monotonic()
            self.assertIn('items', get('/v1/menu?' + query))
            self.assertLess(time.monotonic() - started, 2, query)

    def test_selection_listener_only_bumps_when_the_selection_flips(self):
        listener = self.module.FlexbarBridgeEventListener()
        class Selected(FakeView):
            def id(self): return 4242
        class Empty(NoSelectionView):
            def id(self): return 4242
        self.module._SELECTION_STATE.clear()
        epoch = lambda: self.module.MENU_EPOCH
        e0 = epoch()
        listener.on_selection_modified_async(Selected()); e1 = epoch()
        listener.on_selection_modified_async(Selected()); e2 = epoch()
        listener.on_selection_modified_async(Empty()); e3 = epoch()
        self.assertEqual((e1 - e0, e2 - e1, e3 - e2), (1, 0, 1))

    def test_context_action_keeps_its_slot_and_is_greyed_out(self):
        settings = self.sublime.settings['FlexbarBridge.sublime-settings']
        copy, comment = self._context_action('Auswahl kopieren'), self._context_action('Kommentar')
        settings.set('menu_items', [
            {'type': 'action', 'id': copy['id'], 'label': 'Auswahl kopieren'},
            {'type': 'action', 'id': comment['id'], 'label': 'Kommentar'}])
        shown = lambda: [(i['label'], i['enabled']) for i in self.module.build_menu_state()['items']]
        self.assertEqual(shown(), [('Auswahl kopieren', True), ('Kommentar', True)])
        self.window.view_factory = NoSelectionView          # nothing selected
        self.assertEqual(shown(), [('Auswahl kopieren', False), ('Kommentar', True)])
        self.window.view_factory = lambda: None             # no document at all
        self.assertEqual(shown(), [('Auswahl kopieren', False), ('Kommentar', False)])

    def test_disabled_action_is_not_executed_even_when_requested(self):
        copy = self._context_action('Auswahl kopieren')
        get, url, headers = self._start_server()
        self.window.view_factory = NoSelectionView
        self.window.calls.clear()
        self.module.build_state()
        self.assertFalse(self.module.execute_action(copy['id']))
        request = urllib.request.Request(url + '/v1/action', data=json.dumps({'id': copy['id']}).encode(),
            headers={**headers, 'Content-Type': 'application/json'}, method='POST')
        self.assertEqual(urllib.request.urlopen(request, timeout=3).status, 202)
        self.assertNotIn('copy', [name for name, _ in self.window.calls])
        self.window.view_factory = FakeView                  # selection exists again
        self.assertEqual(urllib.request.urlopen(request, timeout=3).status, 202)
        self.assertIn('copy', [name for name, _ in self.window.calls])

    def test_editor_flags_entries_that_are_currently_unavailable(self):
        settings = self.sublime.settings['FlexbarBridge.sublime-settings']
        settings.set('menu_items', [{'type': 'action', 'id': 'f' * 24, 'label': 'Gelöschter Befehl'}])
        cmd = self.module.FlexbarBridgeMenuEditorCommand(); cmd.window = self.window
        cmd.run()
        self.assertIn('derzeit nicht verfügbar', self.window.sheet.contents)
        save = self._core_action('save')
        settings.set('menu_items', [{'type': 'action', 'id': save['id'], 'label': 'Speichern'}])
        cmd.run()
        self.assertNotIn('derzeit nicht verfügbar', self.window.sheet.contents)

    def test_package_cache_rescans_only_when_something_changed(self):
        module, loads = self.module, []
        original_load, original_find = self.sublime.load_resource, self.sublime.find_resources
        def counting(path, **kw):
            loads.append(path); return original_load(path, **kw)
        self.sublime.load_resource = counting
        self.addCleanup(setattr, self.sublime, 'load_resource', original_load)
        self.addCleanup(setattr, self.sublime, 'find_resources', original_find)
        self.addCleanup(module.CACHE.update, {'at': 0})
        module.CACHE['at'] = 0
        module.package_groups_cached()
        scanned = len(loads)
        self.assertGreater(scanned, 0)
        for _ in range(5):
            module.CACHE['checked'] = 0               # force the cheap fingerprint comparison
            module.package_groups_cached()
        self.assertEqual(len(loads), scanned)          # nothing changed -> palette files are not re-read
        self.sublime.find_resources = lambda pattern: original_find(pattern) + [
            'Packages/NewPlugin/Default.sublime-commands']
        module.CACHE['checked'] = 0
        names = [g['name'] for g in module.package_groups_cached()]
        self.assertGreater(len(loads), scanned)        # a newly installed package is noticed
        self.assertIn('Paket: NewPlugin', names)

    def test_only_palette_files_invalidate_the_package_cache(self):
        listener = self.module.FlexbarBridgeEventListener()
        class Saved(FakeView):
            def __init__(self, name): self.name = name
            def file_name(self): return self.name
        self.addCleanup(self.module.CACHE.update, {'at': 0})
        self.module.package_groups_cached()
        self.assertNotEqual(self.module.CACHE['at'], 0)
        listener.on_post_save_async(Saved('/tmp/notes.txt'))
        self.assertNotEqual(self.module.CACHE['at'], 0)
        listener.on_post_save_async(Saved('/tmp/Packages/X/Default.sublime-commands'))
        self.assertEqual(self.module.CACHE['at'], 0)

    def test_blocked_icons_fall_back_to_text_or_the_automatic_icon(self):
        settings = self.sublime.settings['FlexbarBridge.sublime-settings']
        save = self._core_action('save')
        settings.set('menu_items', [{'type': 'action', 'id': save['id'], 'label': 'Speichern'}])
        icon = lambda: self.module.build_menu_state()['items'][0]['icon']
        self.assertEqual(icon(), 'mdi mdi-content-save')
        for spelling in ('content-save', 'mdi-content-save', 'mdi mdi-content-save'):
            settings.set('blocked_icons', [spelling])
            self.assertIsNone(icon(), spelling)
        settings.set('menu_items', [{'type': 'action', 'id': save['id'], 'label': 'S', 'icon': 'mdi mdi-cog'}])
        settings.set('blocked_icons', ['cog'])
        self.assertEqual(icon(), 'mdi mdi-content-save')   # blocked manual icon -> automatic icon
        settings.set('menu_items', [{'type': 'package', 'name': 'SFTP'}])
        settings.set('blocked_icons', ['cloud-upload'])
        sub = self.module.build_menu_state()['items'][0]['items']
        self.assertIsNone(sub[0]['icon'])
        self.assertEqual(sub[1]['icon'], 'mdi mdi-cloud-download')
        rows = self.module.icon_picker_rows()
        self.assertTrue(any('cloud-upload' in r and '(gesperrt)' in r for r in rows))
        self.assertFalse(any('mdi-cog' in r and '(gesperrt)' in r for r in rows))

    def test_icon_hint_only_for_icons_outside_the_base_list(self):
        messages = []
        original = self.sublime.status_message
        self.sublime.status_message = messages.append
        self.addCleanup(setattr, self.sublime, 'status_message', original)
        self.module.icon_hint('mdi mdi-content-save')
        self.module.icon_hint('__text__')
        self.module.icon_hint(None)
        self.assertEqual(messages, [])
        self.module.icon_hint('mdi mdi-rename')
        self.assertEqual(len(messages), 1)
        self.assertIn('blocked_icons', messages[0])

    # ------------------------------------------------------------ status indicator
    def _reset_status(self, **values):
        m = self.module
        with m.STATUS_LOCK:
            m.STATUS.update({'running': True, 'error': None, 'port': 17864, 'last_seen': 0.0,
                             'activity': 0.0, 'waiting': 0, 'shown': None, **values})

    def test_status_states(self):
        m = self.module
        now = time.time()
        self._reset_status(running=False)
        self.assertEqual(m.status_state(now), 'off')
        self.assertIsNone(m.status_text(now))
        self._reset_status()
        self.assertEqual(m.status_state(now), 'waiting')
        self.assertEqual(m.status_text(now), 'Flexbar ○')
        self._reset_status(last_seen=now - 5)
        self.assertEqual(m.status_text(now), 'Flexbar ●')
        self._reset_status(last_seen=now - 300, waiting=1)
        self.assertEqual(m.status_state(now), 'connected')
        self._reset_status(last_seen=now, activity=now)
        self.assertEqual(m.status_text(now), 'Flexbar ⇅')
        self.assertEqual(m.status_state(now + m.ACTIVITY_SECONDS + 0.1), 'connected')
        self._reset_status(running=False, error='OSError(48)')
        self.assertEqual(m.status_text(now), 'Flexbar ✕')
        self.assertIn('nicht starten', m.status_report(now))
        settings = self.sublime.settings['FlexbarBridge.sublime-settings']
        settings.set('status_indicator', False)
        try:
            self.assertIsNone(m.status_text(now))
        finally:
            settings.data.pop('status_indicator', None)

    def test_status_bar_updated_in_all_views(self):
        m = self.module
        class StatusView:
            def __init__(self): self.status = {}
            def set_status(self, key, text): self.status[key] = text
            def erase_status(self, key): self.status.pop(key, None)
        views = [StatusView(), StatusView()]
        window = types.SimpleNamespace(views=lambda: views)
        self.sublime.windows = lambda: [window]
        self.addCleanup(delattr, self.sublime, 'windows')
        self._reset_status()
        m.refresh_status()
        self.assertEqual([v.status[m.STATUS_KEY] for v in views], ['Flexbar ○'] * 2)
        late = StatusView()
        m._show_status_in(late)
        self.assertEqual(late.status[m.STATUS_KEY], 'Flexbar ○')
        with m.STATUS_LOCK:
            m.STATUS.update(running=False)
        m.refresh_status()
        self.assertTrue(all(m.STATUS_KEY not in v.status for v in views))

    def test_http_requests_mark_client_activity(self):
        m = self.module
        self._reset_status()
        token = secrets.token_hex(32)
        server = m.ThreadingHTTPServer(('127.0.0.1', 0), m.make_handler(token))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = 'http://127.0.0.1:%d/v1/menu' % server.server_port
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url, timeout=1)  # unauthenticated: no contact
            self.assertEqual(m.status_state(), 'waiting')
            req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
            urllib.request.urlopen(req, timeout=2).read()
            self.assertEqual(m.status_state(), 'activity')
            self.assertEqual(m.status_state(time.time() + m.ACTIVITY_SECONDS + 0.1), 'connected')
            self.assertIn('verbunden', m.status_report())
        finally:
            server.shutdown(); server.server_close()

    @unittest.skipUnless(importlib.util.find_spec('material'), 'no local MDI icon set installed')
    def test_curated_icons_exist_in_a_current_mdi_set(self):
        base = os.path.dirname(importlib.util.find_spec('material').origin)
        folder = os.path.join(base, 'templates', '.icons', 'material')
        if not os.path.isdir(folder):
            self.skipTest('MDI folder not found')
        available = {name[:-4] for name in os.listdir(folder) if name.endswith('.svg')}
        missing = sorted(v[len('mdi mdi-'):] for v in self.module.KNOWN_ICONS
                         if v[len('mdi mdi-'):] not in available)
        self.assertEqual(missing, [])


if __name__=='__main__': unittest.main()
