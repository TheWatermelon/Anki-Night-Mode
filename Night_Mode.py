# -*- coding: utf-8 -*-
# Copyright: Michal Krassowski <krassowski.michal@gmail.com>
# License: GNU GPL, version 3 or later; http://www.gnu.org/copyleft/gpl.html
"""
This plugin adds the function of night mode, similar that one implemented in AnkiDroid.

It adds a "view" menu entity (if it doesn't exist) with options like:

    switching night mode
    inverting colors of images or latex formulas
    modifying some of the colors

It provides shortcut ctrl+n to quickly switch mode and color picker to adjust some of color parameters.

After enabling night mode, add-on changes colors of menubar, toolbar, bottombars and content windows.

If you want to contribute visit GitHub page: https://github.com/krassowski/Anki-Night-Mode
Also, feel free to send me bug reports or feature requests.

Copyright: Michal Krassowski <krassowski.michal@gmail.com>
License: GNU GPL, version 3 or later; http://www.gnu.org/copyleft/gpl.html

Special thanks to contributors: [github nickname (reason)]

- b50 (initial compatibility with 2.1),
- ankitest (compatibility with 1508882486),
- omega3 (useful bug reports and suggestions)
- colchizin
- JulyMorning
"""
import traceback

__addon_name__ = "Night Mode"
__version__ = "1.2.3"

from aqt import mw, dialogs
from aqt.editcurrent import EditCurrent
from aqt.addcards import AddCards
from aqt.editor import Editor, EditorWebView
from aqt.clayout import CardLayout
from aqt.browser import Browser, COLOUR_MARKED, COLOUR_SUSPENDED
from aqt.utils import showWarning
from aqt import appVersion


from anki.lang import _
from anki.hooks import addHook
from anki.hooks import wrap
from anki.utils import json


# Anki 2.1
if appVersion.startswith('2.1'):
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtWidgets import (QAction, QMenu, QColorDialog, QMessageBox)
    from PyQt5.QtGui import(QKeySequence, QColor)
    from PyQt5 import QtCore
# Anki 2.0
else:
    from PyQt4.QtCore import SIGNAL
    from PyQt4.QtGui import (QAction, QKeySequence, QMenu, QColorDialog,
                             QMessageBox, QColor)
    from PyQt4 import QtCore

from os.path import isfile

from colors import wal
theme = wal()

try:
    nm_from_utf8 = QtCore.QString.fromUtf8
except AttributeError:
    nm_from_utf8 = lambda s: s

# Add here you color replacements mapping - old: new, comma separated
nm_custom_color_map = {
        '#007700': '#30DC16',
        '#000099': '#00BBFF',
        '#C35617': '#D46728',
        '#00a': '#00BBFF'
        }

# This declarations are there only to be sure that in case of troubles
# with "profileLoaded" hook everything will work.

nm_state_on = False
nm_enable_in_dialogs = True
nm_invert_image = False
nm_invert_latex = False
nm_transparent_latex = False
nm_profile_loaded = False

nm_menu_switch = None
nm_menu_iimage = None
nm_menu_ilatex = None
nm_menu_endial = None
nm_menu_tlatex = None

nm_color_bl = theme.color1 # background color (customizable from menu)
nm_color_bd = theme.color0
nm_color_s = theme.color0  # alternative (second) background color (hardcoded)
nm_color_tl = "#ffffff"
nm_color_td = theme.foreground  # text color (customizable from menu)
nm_color_al = theme.color4 # active element color (hardcoded)
nm_color_ad = theme.color3

# Save original values for further use.
nm_default_css_menu = mw.styleSheet()

nm_default_css_top = mw.toolbar._css
if not appVersion.startswith('2.1'):
    nm_default_css_body = mw.reviewer._css
else:
    nm_default_css_body = ''
    nm_default_reviewer_html = mw.reviewer._revHtml
nm_default_css_bottom = mw.reviewer._bottomCSS

nm_default_css_decks = mw.deckBrowser._css
nm_default_css_decks_bottom = mw.deckBrowser.bottom._css

nm_default_css_overview = mw.overview._css
nm_default_css_overview_bottom = mw.overview.bottom._css
# sharedCSS is only used for "Waiting for editing to finish." screen.
nm_default_css_waiting_screen = mw.sharedCSS

DEFLAULT_COLOUR_MARKED = COLOUR_MARKED
DEFLAULT_COLOUR_SUSPENDED = COLOUR_SUSPENDED


def nm_css_custom_color_map():
    css = ''
    for old, new in nm_custom_color_map.items():
        css += 'font[color="' + old + '"]{color:' + new + '!important}'
    return css


def nm_iimage():
    """
    Toggles image inversion.
    To learn how images are inverted check also nm_append_to_styles().
    """
    global nm_invert_image
    nm_invert_image = not nm_invert_image
    nm_refresh()


def nm_ilatex():
    """
    Toggles latex inversion.
    Latex formulas are nothing more than images with class "latex".
    To learn how formulas are inverted check also nm_append_to_styles().
    """
    global nm_invert_latex
    nm_invert_latex = not nm_invert_latex
    nm_refresh()


def nm_tlatex():
    """Toggles transparent latex generation.

    See nm_make_latex_transparent() for details.
    """
    global nm_transparent_latex
    nm_transparent_latex = not nm_transparent_latex
    if nm_transparent_latex:
        nm_make_latex_transparent()


def nm_make_latex_transparent():
    """Overwrite latex generation commands to use transparent images.

    Already generated latex images won't be affected;
    delete those manually from your media folder in order
    to regenerate images in transparent version.
    """
    commands = []

    if appVersion.startswith('2.1'):
        from anki.latex import pngCommands
        from anki.latex import svgCommands
        commands.extend([pngCommands, svgCommands])
    else:
        from anki.latex import latexCmds
        commands.append(latexCmds)

    for command in commands:
        command[1] = [
            "dvipng",
            "-D", "200",
            "-T", "tight",
            "-bg", "Transparent",
            "-z", "9",  # use maximal PNG compression
            "tmp.dvi",
            "-o", "tmp.png"
        ]


def nm_change_color_t():
    """
    Open color picker and set chosen color to text (in content)
    """
    global nm_color_td
    nm_qcolor_old = QColor(nm_color_td)
    nm_qcolor = QColorDialog.getColor(nm_qcolor_old)
    if nm_qcolor.isValid():
        nm_color_td = nm_qcolor.name()
        nm_refresh()


def nm_change_color_b():
    """
    Open color picker and set chosen color to background (of content)
    """
    global nm_color_bl
    nm_qcolor_old = QColor(nm_color_bl)
    nm_qcolor = QColorDialog.getColor(nm_qcolor_old)
    if nm_qcolor.isValid():
        nm_color_bl = nm_qcolor.name()
        nm_refresh()


def nm_color_reset():
    """
    Reset colors.
    """
    global nm_color_bl, nm_color_td
    nm_color_bl = theme.color1
    nm_color_td = theme.color7
    nm_refresh()


def nm_about():
    """
    Show "about" window.
    """
    nm_about_box = QMessageBox()
    if nm_state_on:
        nm_about_box.setStyleSheet(nm_message_box_css())
    nm_about_box.setText(__addon_name__ + " " + __version__ + __doc__)
    nm_about_box.setGeometry(300, 300, 250, 150)
    nm_about_box.setWindowTitle("About " + __addon_name__ + " " + __version__)

    nm_about_box.exec_()


def nm_save():
    """
    Saves configurable variables into profile, so they can
    be used to restore previous state after Anki restart.
    """
    mw.pm.profile['nm_state_on'] = nm_state_on
    mw.pm.profile['nm_enable_in_dialogs'] = nm_enable_in_dialogs
    mw.pm.profile['nm_invert_image'] = nm_invert_image
    mw.pm.profile['nm_invert_latex'] = nm_invert_latex
    mw.pm.profile['nm_transparent_latex'] = nm_transparent_latex
    mw.pm.profile['nm_color_bl'] = nm_color_bl
    mw.pm.profile['nm_color_td'] = nm_color_td


def nm_load():
    """
    Load configuration from profile, set states of checkable menu objects
    and turn on night mode if it were enabled on previous session.
    """
    global nm_menu_iimage, nm_menu_ilatex, nm_state_on, \
        nm_invert_image, nm_invert_latex, nm_color_bl, nm_color_td, \
        nm_enable_in_dialogs, nm_profile_loaded, nm_transparent_latex

    nm_state_on = mw.pm.profile.get('nm_state_on', True)
    nm_invert_image = mw.pm.profile.get('nm_invert_image', False)
    nm_invert_latex = mw.pm.profile.get('nm_invert_latex', False)
    nm_color_bl = mw.pm.profile.get('nm_color_bl', theme.color1)
    nm_color_td = mw.pm.profile.get('nm_color_td', theme.color7)
    nm_enable_in_dialogs = mw.pm.profile.get('nm_enable_in_dialogs', True)
    nm_transparent_latex = mw.pm.profile.get('nm_transparent_latex', False)

    nm_refresh_css_custom_colors_string()

    nm_profile_loaded = True

    if nm_state_on:
        nm_on()

    if nm_invert_image:
        nm_menu_iimage.setChecked(True)

    if nm_invert_latex:
        nm_menu_ilatex.setChecked(True)

    if nm_enable_in_dialogs:
        nm_menu_endial.setChecked(True)

    if nm_transparent_latex:
        nm_menu_tlatex.setChecked(True)
        nm_make_latex_transparent()


def nm_style_fields(editor):

    if nm_state_on and nm_enable_in_dialogs:

        cols = []
        for f in editor.note.fields:
            cols.append(nm_color_tl)
        err = editor.note.dupeOrEmpty()
        if err == 2:
            cols[0] = "#A96D06"
            editor.web.eval("showDupes();")
        else:
            editor.web.eval("hideDupes();")
        editor.web.eval("setBackgrounds(%s);" % json.dumps(cols))


def nm_set_style_to_objects_inside(layout, style):
    for i in range(layout .count()):
        layout.itemAt(i).widget().setStyleSheet(style)


def nm_editor_init_after(self, mw, widget, parentWindow, addMode=False):

    if nm_state_on and nm_enable_in_dialogs:

        editor_css = nm_dialog_css()

        editor_css += '#' + widget.objectName() + '{ background:' + theme.color1 + '; color:' + theme.color7 + '; }'

        self.parentWindow.setStyleSheet(editor_css)

        self.tags.completer.popup().setStyleSheet(nm_css_completer)

        widget.setStyleSheet(
            nm_css_qt_mid_buttons +
            nm_css_qt_buttons(restrict_to='#' + nm_encode_class_name('fields')) +
            nm_css_qt_buttons(restrict_to='#' + nm_encode_class_name('layout'))
        )


def nm_editor_loadFinished(self):
    if nm_state_on and nm_enable_in_dialogs:
        self.web.eval("setBG('%s')" % nm_color_bl)


def nm_editor_web_view_stdHTML_around(*args, **kwargs):
    """For use in 2.1"""
    custom_css = ''
    original_function = kwargs.pop('_old')

    if nm_state_on and nm_enable_in_dialogs:
        custom_css += nm_css_buttons + '.topbut{filter:invert(1); -webkit-filter:invert(1)}'
        custom_css += 'a{color:' + nm_color_tl + '}  .fname, .field{  }'
        custom_css += 'html,body{background:#fff!important}'

    if nm_invert_image:
        custom_css += ".field " + nm_css_iimage
    if nm_invert_latex:
        custom_css += ".field " + nm_css_ilatex

    args = list(args)

    import inspect

    signature = inspect.signature(original_function)
    i = 0
    for name, parameter in signature.parameters.items():
        if i >= len(args):
            break
        if parameter.default is not inspect._empty:
            value = args.pop(i)
            kwargs[name] = value
        else:
            i += 1

    kwargs['css'] = kwargs.get('css', '') + custom_css

    return original_function(*args, **kwargs)


def nm_editor_web_view_set_html_after(self, *args, **kwargs):
    """Used in 2.0"""
    css = ''

    if nm_state_on and nm_enable_in_dialogs:
        css += 'a{color:' + nm_color_tl + '}'
        css += """
        .fname
        { 
            background:""" + theme.color1 + """; 
            color:""" + theme.color7 + """;
        }
        *::selection
        {
            background: """ + nm_color_al + """;
            color: """ + nm_color_tl + """;
        }
        """
        css += nm_css_scrollbar()

    if nm_invert_image:
        css += '.field ' + nm_css_iimage
    if nm_invert_latex:
        css += '.field ' + nm_css_ilatex

    javascript = "var node=document.createElement('style');"
    javascript += "node.innerHTML='" + css.replace("\n", ' ') + "';"
    javascript += "document.body.appendChild(node);"

    self.eval(javascript)


def nm_edit_current_init_after(self, mw):

    if nm_state_on and nm_enable_in_dialogs:
        x = self.styleSheet()
        self.setStyleSheet(x + nm_css_scrollbar())
        self.form.buttonBox.setStyleSheet(nm_css_qt_buttons())


def nm_browser_init_after(self, mw):

    if nm_state_on and nm_enable_in_dialogs:

        x = self.styleSheet()
        self.setStyleSheet(x + nm_css_menu + nm_css_browser())
        self.toolbar._css += nm_css_top
        self.toolbar.draw()

        self.form.tableView.setStyleSheet(nm_browser_table_css())
        self.form.tableView.horizontalHeader().setStyleSheet(nm_browser_table_header_css())

        self.form.searchEdit.setStyleSheet(nm_browser_search_box_css())
        self.form.searchButton.setStyleSheet(nm_css_qt_buttons())
        self.form.previewButton.setStyleSheet(nm_css_qt_buttons())


def nm_browser_card_info_after(self, _old):

    rep, cs = _old(self)

    if nm_state_on and nm_enable_in_dialogs:
        rep += """
            <style>
            *
            {
                """ + nm_css_custom_colors + """
            }
            div
            {
                border-color:#fff!important
            }
            """ + nm_css_color_replacer + """
            """ + nm_css_scrollbar() + """
            </style>
            """
    return rep, cs


def nm_add_init_after(self, mw):

    if nm_state_on and nm_enable_in_dialogs:

        self.form.buttonBox.setStyleSheet(nm_css_qt_buttons())
        nm_set_style_to_objects_inside(self.form.horizontalLayout, nm_css_qt_buttons())
        self.form.line.setStyleSheet("#" + nm_from_utf8("line") + "{border:0px solid transparent}")
        self.form.fieldsArea.setAutoFillBackground(False)


def take_care_of_night_class(web_object=None):

    if not web_object:
        web_object = mw.reviewer.web

    if nm_state_on:
        javascript = """
        current_classes = document.body.className;
        if(current_classes.indexOf("night_mode") == -1)
        {
            document.body.className += " night_mode";
        }
        """
    else:
        javascript = """
        current_classes = document.body.className;
        if(current_classes.indexOf("night_mode") != -1)
        {
            document.body.className = current_classes.replace("night_mode","");
        }
        """

    web_object.eval(javascript)


def nm_encode_class_name(string):
    return "ID"+"".join(map(str, map(ord, string)))


def nm_add_button_name(self, name, *args, **kwargs):
    original_function = kwargs.pop('_old')
    button = original_function(self, name, *args, **kwargs)
    if name:
        button.setObjectName(nm_encode_class_name(name))
    return button


def nm_add_class_to_editor_button(self, icon, command, *args, **kwargs):
    original_function = kwargs.pop('_old')
    button = original_function(self, icon, command, *args, **kwargs)
    return button.replace('<button>', '<button class="editor-btn">')


def nm_render_preview_after(card_layout):

    take_care_of_night_class(card_layout.tab['pform'].frontWeb)
    take_care_of_night_class(card_layout.tab['pform'].backWeb)


def nm_edit_render_preview_after(browser, cardChanged=False):
    if not browser._previewWindow:
        return
    take_care_of_night_class(browser._previewWeb)


def nm_onload():
    """
    Add hooks and initialize menu.
    Call to this function is placed on the end of this file.
    """

    nm_refresh_css_custom_colors_string()

    addHook("unloadProfile", nm_save)
    addHook("profileLoaded", nm_load)
    addHook("showQuestion", take_care_of_night_class)
    addHook("showAnswer", take_care_of_night_class)
    nm_setup_menu()

    Browser.__init__ = wrap(Browser.__init__, nm_browser_init_after)
    if appVersion.startswith('2.1'):
        Editor._addButton = wrap(Editor._addButton, nm_add_class_to_editor_button, "around")
    else:
        Editor._addButton = wrap(Editor._addButton, nm_add_button_name, "around")
    Editor.checkValid = wrap(Editor.checkValid, nm_style_fields)
    Editor.__init__ = wrap(Editor.__init__, nm_editor_init_after)

    # Anki 2.1 Deck Browser background colour
    if appVersion.startswith('2.1'):
        # Editor._loadFinished = wrap(Editor._loadFinished, nm_editor_loadFinished)
        EditorWebView.stdHtml = wrap(EditorWebView.stdHtml, nm_editor_web_view_stdHTML_around, "around")
    else:
        EditorWebView.setHtml = wrap(EditorWebView.setHtml, nm_editor_web_view_set_html_after)

    Browser._renderPreview = wrap(Browser._renderPreview, nm_edit_render_preview_after)
    Browser._cardInfoData = wrap(Browser._cardInfoData, nm_browser_card_info_after, "around")
    EditCurrent.__init__ = wrap(EditCurrent.__init__, nm_edit_current_init_after)
    AddCards.__init__ = wrap(AddCards.__init__, nm_add_init_after)
    CardLayout.renderPreview = wrap(CardLayout.renderPreview, nm_render_preview_after)


def nm_append_to_styles(bottom='', body='', top='', decks='',
                        other_bottoms='', overview='', menu='',
                        waiting_screen=''):
    """
    This function changes CSS style of most objects. In basic use,
    it only reloads original styles and refreshes interface.

    All arguments are expected to be strings with CSS styles.
    """
    # Invert images and latex if needed
    if nm_invert_image:
        body += nm_css_iimage
    if nm_invert_latex:
        body += nm_css_ilatex

    # Apply styles to Python objects or by Qt functions.

    mw.setStyleSheet(nm_default_css_menu + menu)
    mw.toolbar._css = nm_default_css_top + top
    mw.reviewer._bottomCSS = nm_default_css_bottom + bottom

    if not appVersion.startswith('2.1'):
        mw.reviewer._css = nm_default_css_body + body + nm_css_scrollbar()
    else:
        mw.reviewer._revHtml = nm_default_reviewer_html + '<style>' + body + '</style>'

    mw.deckBrowser._css = nm_default_css_decks + decks
    mw.deckBrowser.bottom._css = nm_default_css_decks_bottom + other_bottoms
    mw.overview._css = nm_default_css_overview + overview
    mw.overview.bottom._css = nm_default_css_overview_bottom + other_bottoms
    mw.sharedCSS = nm_default_css_waiting_screen + waiting_screen

    # Reload current screen.
    if mw.state == "review":
        mw.reviewer._initWeb()
    if mw.state == "deckBrowser":
        mw.deckBrowser.refresh()
    if mw.state == "overview":
        mw.overview.refresh()

    # Redraw toolbar (should be always visible).
    mw.toolbar.draw()


def nm_on():
    """Turn on night mode."""
    if not nm_profile_loaded:
        showWarning(NM_ERROR_NO_PROFILE)
        return False

    global nm_state_on

    try:
        nm_state_on = True

        import aqt.browser
        aqt.browser.COLOUR_MARKED = "#D9B2E9"
        aqt.browser.COLOUR_SUSPENDED = "#FFFFB2"

        nm_append_to_styles(
            bottom=nm_css_bottom,
            body=nm_css_body + nm_card_color_css() + nm_css_custom_color_map(),
            top=nm_css_top,
            decks=nm_css_decks + nm_body_color_css(),
            other_bottoms=nm_css_other_bottoms,
            overview=nm_css_overview() + nm_body_color_css(),
            menu=nm_css_menu,
            waiting_screen=nm_css_buttons + nm_body_color_css()
        )
        nm_menu_switch.setChecked(True)
        return True
    except Exception as e:
        showWarning(NM_ERROR_SWITCH % traceback.format_exc())
        return False


def nm_off():
    """Turn off night mode."""
    if not nm_profile_loaded:
        showWarning(NM_ERROR_NO_PROFILE)
        return False

    try:
        global nm_state_on
        nm_state_on = False

        import aqt.browser
        aqt.browser.COLOUR_MARKED = DEFLAULT_COLOUR_MARKED
        aqt.browser.COLOUR_SUSPENDED = DEFLAULT_COLOUR_SUSPENDED

        nm_append_to_styles()
        nm_menu_switch.setChecked(False)
        return True
    except Exception as e:
        showWarning(NM_ERROR_SWITCH % traceback.format_exc())
        return False


def nm_switch():
    """
    Switch night mode.
    """

    # Implementation of "setStyleSheet" method in QT is bugged.
    # At some circumstances it causes a seg fault, without throwing any exceptions.
    # So the switch of mode is not allowed when the problematic dialogs are visible.
    is_active_dialog = filter(bool, [x[1] for x in dialogs._dialogs.values()])

    if appVersion.startswith('2.0') and is_active_dialog:
        info = _("Night mode can not be switched when the dialogs are open")
        showWarning(info)
    else:
        if nm_state_on:
            nm_off()
        else:
            nm_on()


def nm_endial():
    """
    Switch for night mode in dialogs
    """
    global nm_enable_in_dialogs
    if nm_enable_in_dialogs:
        nm_enable_in_dialogs = False
    else:
        nm_enable_in_dialogs = True


def nm_refresh():
    """
    Refresh display by re-enabling night or normal mode,
    regenerate customizable css strings.
    """

    nm_refresh_css_custom_colors_string()

    if nm_state_on:
        nm_on()
    else:
        nm_off()


def nm_setup_menu():
    """
    Initialize menu. If there is an entity "View" in top level menu
    (shared with other plugins, like "Zoom" of R. Sieker) options of
    Night Mode will be putted there. In other case it creates that menu.
    """
    global nm_menu_switch, nm_menu_iimage, nm_menu_ilatex, nm_menu_endial, nm_menu_tlatex

    try:
        mw.addon_view_menu
    except AttributeError:
        mw.addon_view_menu = QMenu(_(u"&View"), mw)

        mw.form.menubar.insertMenu(
            mw.form.menuTools.menuAction(),
            mw.addon_view_menu
        )

    mw.nm_menu = QMenu(_('&Night Mode'), mw)

    mw.addon_view_menu.addMenu(mw.nm_menu)

    nm_menu_switch = QAction(_('&Enable night mode'), mw, checkable=True)
    #nm_menu_iimage = QAction(_('&Invert images'), mw, checkable=True)
    #nm_menu_ilatex = QAction(_('Invert &latex'), mw, checkable=True)
    nm_menu_endial = QAction(_('Enable in &dialogs'), mw, checkable=True)
    #nm_menu_tlatex = QAction(_('Force transparent latex'), mw, checkable=True)
    nm_menu_color_b = QAction(_('Set &background color'), mw)
    nm_menu_color_t = QAction(_('Set &text color'), mw)
    nm_menu_color_r = QAction(_('&Reset colors'), mw)
    nm_menu_about = QAction(_('&About...'), mw)

    mw_toggle_seq = QKeySequence("Ctrl+n")
    nm_menu_switch.setShortcut(mw_toggle_seq)

    mw.nm_menu.addAction(nm_menu_switch)
    mw.nm_menu.addAction(nm_menu_endial)
    mw.nm_menu.addSeparator()
    #mw.nm_menu.addAction(nm_menu_iimage)
    #mw.nm_menu.addAction(nm_menu_ilatex)
    #mw.nm_menu.addAction(nm_menu_tlatex)
    mw.nm_menu.addSeparator()
    mw.nm_menu.addAction(nm_menu_color_b)
    mw.nm_menu.addAction(nm_menu_color_t)
    mw.nm_menu.addAction(nm_menu_color_r)
    mw.nm_menu.addSeparator()
    mw.nm_menu.addAction(nm_menu_about)

    connections = {
        nm_menu_endial: nm_endial,
        nm_menu_switch: nm_switch,
        #nm_menu_iimage: nm_iimage,
        #nm_menu_ilatex: nm_ilatex,
        #nm_menu_tlatex: nm_tlatex,
        nm_menu_color_b: nm_change_color_b,
        nm_menu_color_t: nm_change_color_t,
        nm_menu_color_r: nm_color_reset,
        nm_menu_about: nm_about,
    }

    # Anki 2.1
    if appVersion.startswith('2.1'):
        def connect(menu_entry, function):
            menu_entry.triggered.connect(function)
    # Anki 2.0
    else:
        s = SIGNAL("triggered()")

        def connect(menu_entry, function):
            mw.connect(menu_entry, s, function)

    for menu_entry, function in connections.items():
        connect(menu_entry, function)


def nm_make_css_custom_colors_string():
    return 'color:' + nm_color_td + ';\n' \
    + 'background:' + nm_color_bl + ';'


def nm_refresh_css_custom_colors_string():
    global nm_css_custom_colors
    nm_css_custom_colors = nm_make_css_custom_colors_string()

#
# QT CSS STYLES SECTION
#

def nm_card_color_css():
    """
    Generate and return CSS style of class "card",
    using global color declarations
    """
    return (".card {    color:" + nm_color_td + "!important;" +
            "background-color:#blue!important}")


def nm_body_color_css():
    """
    Generate and return CSS style of body
    using global color declarations
    """
    return (" body {    color:" + nm_color_td + "!important;" +
            "background-color:!important}")


def nm_message_box_css():
    """
    Generate and return CSS style of class QMessageBox,
    using global color declarations
    """
    return ("QMessageBox,QLabel { background:yellow; }" + nm_css_qt_buttons() +
            "QPushButton {min-width:70px}")


def nm_css_qt_buttons(restrict_to_parent="", restrict_to=""):
    return """
    """ + restrict_to_parent + """ QPushButton""" + restrict_to + """
    {
        border-radius: 3px;
        """ + nm_css_button_idle + """
    }
    """ + restrict_to_parent + """ QPushButton""" + restrict_to + """:hover
    {
        """ + nm_css_button_hover + """
    }
    """ + restrict_to_parent + """ QPushButton""" + restrict_to + """:pressed
    {
        """ + nm_css_button_active + """
    }
    """ + restrict_to_parent + """ QPushButton""" + restrict_to + """:focus
    {
        outline: 1px dotted #4a90d9
    }
    """


def nm_dialog_css():
    """
    Generate and return CSS style of AnkiQt Dialogs,
    using global color declarations
    """
    return """
            QLabel
            {
                color: """ + theme.color7 + """;
            }
            QDialog
            {
                background: """ + theme.color1 + """;
            }
            QFontComboBox::drop-down
            {
                border: 0px; 
                border-left: 1px solid """ + nm_color_al + """; 
                width: 30px;
            }
            QFontComboBox::down-arrow{width:12px; height:8px;
                top:1px;
                image:url(""" + NM_DOWN_ARROW_ICON_PATH + """)
            }
            QFontComboBox, QSpinBox
            {
                border: 1px solid """ + nm_color_al + """;
            }

            QTabWidget QWidget
            {
                border-color:""" + nm_color_al + """;
            }
            QTabWidget QLabel {
                position:relative
            }
            QTabWidget QTabBar
            {
                background: """ + theme.color1 + """;
                color: """ + theme.color7 + """;
            }
            QTabWidget QTextEdit
            {
                border-color:""" + nm_color_al + """;
            }
            QTabWidget QGroupBox::title
            {
                subcontrol-origin: margin;
                subcontrol-position:top left;
                margin-top:-7px
            }
            """ + nm_css_qt_buttons("QTabWidget")


def nm_browser_table_css():
    return """
        QTableView
        {
            gridline-color:""" + nm_color_td + """;
            selection-background-color: """ + nm_color_al + """
        }
        """


def nm_browser_table_header_css():
    return """
        QHeaderView, QHeaderView::section
        {
            background: """ + theme.color1 + """;
            color: #fff;
            border: 0px;
            border-top:1px solid """ + nm_color_al + """;
            border-bottom:1px solid """ + nm_color_al + """;
        }
        """


def nm_browser_search_box_css():
    return """
    QComboBox
    {
        border:2px solid """ + nm_color_al + """;
        border-radius:3px;
        padding:0px 4px;
        background: #fff;
        selection-background-color: """ + nm_color_al + """;
        color: #000;
    }

    QComboBox:!editable
    {
        background:""" + nm_color_al + """
    }

    QComboBox QAbstractItemView
    {
        border:1px solid """ + nm_color_al + """;
        selection-background-color: """ + nm_color_al + """;
    }

    QComboBox::drop-down, QComboBox::drop-down:editable
    {
        width:24px;
        border-left:1px solid """ + nm_color_al + """;
        border-top-right-radius:3px;
        border-bottom-right-radius:3px;
    }

    QComboBox::down-arrow
    {
        top:1px;
        image: url(""" + NM_DOWN_ARROW_ICON_PATH + """)
    }
    """


def nm_css_browser():
    return """
    QSplitter::handle
    {
        background:""" + theme.color1 + """;
    }
    #""" + nm_from_utf8("widget") + """
    {
        background: """ + theme.color1 + """;
    }
    QTreeView
    {
        background: """ + theme.color0 + """;
        color: """ + theme.color7 + """;
    }
    QTreeView::item:selected:active, QTreeView::branch:selected:active
    {
        background:""" + nm_color_al + """
    }
    QTreeView::item:selected:!active, QTreeView::branch:selected:!active
    {
        background:""" + nm_color_al + """
    }
    """ + nm_css_scrollbar()


def nm_css_scrollbar():
    return """
        QScrollBar:vertical {
            width: 10px;
            background: """ + theme.color7 + """;
        }
        QScrollBar::handle:vertical {
            background: """ + theme.color4 + """;
            min-height: 3px;
            border-radius: 3px;
            margin: 2px 2px 2px 2px;
        }
        QScrollBar::add-line:vertical
        {
            height: 0px;
            subcontrol-position: bottom;
            subcontrol-origin: margin;
        }
        QScrollBar::sub-line:vertical
        {
            height: 0px;
            subcontrol-position: top;
            subcontrol-origin: margin;
        }
        QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical 
        {
            width: 5px;
            height: 5px;
            background: """ + theme.color1 + """;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical
        {
            background: none;
        }
        QScrollBar:horizontal {
            height: 10px;
            background: """ + theme.color7 + """;
        }
        QScrollBar::handle:horizontal {
            background: """ + theme.color4 + """;
            min-width: 3px;
            border-radius: 3px;
            margin: 2px 2px 2px 2px;
        }
        QScrollBar::add-line:horizontal
        {
            width: 0px;
            subcontrol-position: bottom;
            subcontrol-origin: margin;
        }
        QScrollBar::sub-line:horizontal
        {
            width: 0px;
            subcontrol-position: top;
            subcontrol-origin: margin;
        }
        QScrollBar::up-arrow:horizontal, QScrollBar::down-arrow:horizontal 
        {
            width: 5px;
            height: 5px;
            background: """ + theme.color1 + """;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal
        {
            background: none;
        }
        ::-webkit-scrollbar
        {
            height: 10px;
            width: 10px;
        }
        /* background */
        ::-webkit-scrollbar-track
        {
            background:""" + theme.color7 + """;
        }
        /* handle */
        ::-webkit-scrollbar-thumb
        {
            min-height: 3px;
            min-width: 3px;
            border-radius: 3px;
            border: 2px solid """ + theme.color7 + """;
            background:""" + theme.color4 + """;
        }
        """


#
# GLOBAL CSS STYLES SECTION
#

nm_css_custom_colors = nm_make_css_custom_colors_string()


# Thanks to http://devgrow.com/dark-button-navigation-using-css3/
nm_css_button_idle = """
    background:""" + nm_color_bl + """;
    color:""" + nm_color_tl + """;
    margin-top:5px;
    position:relative;
    top:0;
    padding:3px 8px;
    border:1px solid #3E474D;
    border-top-color:#1c252b;
    border-left-color:#2d363c;
"""

nm_css_button_hover = """
    background: """ + nm_color_ad + """;
    color:""" + nm_color_tl + """;
"""

nm_css_button_active = """
    background: """ + nm_color_al + """;
    color:""" + nm_color_tl + """;
"""

nm_css_buttons = """
button
{
    """ + nm_css_button_idle + """
    text-shadow:1px 1px #1f272b;
    display:inline-block;
    -webkit-box-shadow:1px 1px 1px rgba(0,0,0,0.1);
    -webkit-border-radius:3px
}
button:hover
{
    """ + nm_css_button_hover + """
}
button:active
{
    """ + nm_css_button_active + """
    -webkit-box-shadow:1px 1px 1px rgba(255,255,255,0.1);
}
"""

nm_css_completer = """
    selection-background-color:""" + nm_color_al + """;
    border:1px solid """ + nm_color_al + """;
"""

nm_css_qt_mid_buttons = """
QLineEdit
{
    background: #fff;
    selection-background-color: """ + nm_color_al + """;
    color: black;
    border:1px solid """ + nm_color_al + """;
}
"""

nm_css_color_replacer = """
font[color="#007700"],span[style="color:#070"]
{
    color:#30dc16!important
}
font[color="#000099"],span[style="color:#00F"]
{
    color:#00BBFF!important
}
font[color="#C35617"],span[style="color:#c00"]
{
    color:#E79292!important
}
font[color="#00a"]
{
    color:#00BBFF
}
"""

nm_css_bottom = nm_css_buttons + nm_css_color_replacer + """
body, #outer
{
    background: """ + nm_color_bl + """;
    color: """ + nm_color_tl + """;
    border-top-color:""" + nm_color_al + """;
}
.stattxt
{
    color:""" + nm_color_td + """;
}
/* Make the color above "Again" "Hard" "Easy" and so on buttons readable */
.nobold
{
    color:""" + nm_color_tl + """;
}
"""

nm_css_top = """
html, #header
{
    """ + nm_css_custom_colors + """;
}
body, #header
{
    """ + nm_css_custom_colors + """;
    border-bottom-color:""" + nm_color_al + """;
}
.hitem
{
    color:""" + nm_color_tl + """;
}
"""

nm_css_ilatex = """\
.latex
{
    filter:invert(1);
    -webkit-filter:invert(1)
}
"""

nm_css_iimage = """\
img
{
    filter:invert(1);
    -webkit-filter:invert(1)
}
"""


nm_css_body = """
.card input
{
    background-color:red!important;
    border-color:blue!important;
    color:#eee!important
}
.card label
{
    margin-top: 5px;
    color: """ + theme.color7 + """;
}
.typeGood
{
    color:black;
    background:#30dc16
}
.typeBad
{
    color:black;
    background:#c43c35
}
.typeMissed
{
    color:black;
    background:#ccc
}
#answer
{
    height:0;
}
img#star
{
    -webkit-filter:invert(0%)!important
}
.cloze
{
    color:#5566ee!important
}
a
{
    color:#0099CC
}
"""

nm_css_decks = nm_css_buttons + nm_css_color_replacer + """
a
{
    color:""" + nm_color_tl + """;
}
.current
{
    background-color:#e7e7e7;
}
a.deck, .collapse
{
    color: #000;
}
tr.deck td
{
    height:35px;
}
tr.deck button img
{
    -webkit-filter:invert(20%)
}
tr.deck font[color="#007700"]
{
    color:#30dc16
}
tr.deck font[color="#000099"]
{
    color:#00BBFF
}
.filtered
{
    color:#00AAEE!important
}
"""

nm_css_other_bottoms = nm_css_buttons + """
#header
{
    background: """ + nm_color_bl + """;
    color:""" + nm_color_td + """!important;
    border-top-color:""" + nm_color_al + """;
    height:40px
}
"""


def nm_css_overview():
    return nm_css_buttons + """
    .descfont
    {
    }
    """

nm_css_menu = """
QMenuBar,QMenu
{
    background-color:""" + nm_color_bl + """!important;
    color:""" + nm_color_td + """!important;
}
QMenuBar::item
{
    background-color:transparent
}
QMenuBar::item:selected
{
    background-color:""" + nm_color_al + """!important;
    color:""" + nm_color_tl + """!important;
}
QMenu
{
    border:1px solid """ + nm_color_al + """;
}
QMenu::item::selected
{
    background-color:""" + nm_color_al + """;
    color:""" + nm_color_tl + """;
}
QMenu::item
{
    padding:3px 25px 3px 25px;
    border:1px solid transparent
}
"""

NM_ERROR_NO_PROFILE = """Switching night mode failed: The profile is not loaded yet.
Probably it's a bug of Anki or you tried to switch mode to quickly."""

NM_ERROR_SWITCH = """Switching night mode failed: Something went really really wrong.
Contact add-on author to get help.

Please provide following traceback when reporting the issue:
%s
"""


where_to_look_for_arrow_icon = [
    '/usr/share/icons/Adwaita/scalable/actions/pan-down-symbolic.svg',
    '/usr/share/icons/gnome/scalable/actions/go-down-symbolic.svg',
    '/usr/share/icons/ubuntu-mobile/actions/scalable/dropdown-menu.svg',
    '/usr/share/icons/Humanity/actions/16/down.svg',
    '/usr/share/icons/Humanity/actions/16/go-down.svg',
    '/usr/share/icons/Humanity/actions/16/stock_down.svg',
    '/usr/share/icons/nuvola/16x16/actions/arrow-down.png',
    '/usr/share/icons/default.kde4/16x16/actions/arrow-down.png'
]

# It's not an arrow icon,
# but on windows systems it's better to have this, than nothing.
NM_DOWN_ARROW_ICON_PATH = ':/icons/gears.png'

for path in where_to_look_for_arrow_icon:
    if isfile(path):
        NM_DOWN_ARROW_ICON_PATH = path
        break

#
# ONLOAD SECTION
#

nm_onload()
