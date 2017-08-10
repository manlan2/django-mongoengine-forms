import copy

from django.forms.widgets import (Widget, Media, TextInput, FileInput,
                                  SplitDateTimeWidget, DateInput, TimeInput,
                                  MultiWidget, HiddenInput, CheckboxInput)
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.core.validators import EMPTY_VALUES
from django.forms.utils import flatatt


class Html5SplitDateTimeWidget(SplitDateTimeWidget):
    def __init__(self, attrs=None, date_format=None, time_format=None):
        date_input = DateInput(attrs=attrs, format=date_format)
        date_input.input_type = 'date'
        time_input = TimeInput(attrs=attrs, format=time_format)
        time_input.input_type = 'time'
        widgets = (date_input, time_input)
        MultiWidget.__init__(self, widgets, attrs)


class BaseContainerWidget(Widget):
    def __init__(self, data_widget, attrs=None):
        if isinstance(data_widget, type):
            data_widget = data_widget()
        self.data_widget = data_widget
        self.data_widget.is_localized = self.is_localized
        super(BaseContainerWidget, self).__init__(attrs)

    def id_for_label(self, id_):
        # See the comment for RadioSelect.id_for_label()
        if id_:
            id_ += '_0'
        return id_

    def format_output(self, rendered_widgets):
        """
        Given a list of rendered widgets (as strings), returns a Unicode string
        representing the HTML for the whole lot.

        This hook allows you to format the HTML design of the widgets, if
        needed.
        """
        return ''.join(rendered_widgets)

    def _get_media(self):
        """
        Media for a multiwidget is the combination of all media of
        the subwidgets.
        """
        media = Media()
        media = media + self.data_widget.media
        return media
    media = property(_get_media)

    def __deepcopy__(self, memo):
        obj = super(BaseContainerWidget, self).__deepcopy__(memo)
        obj.data_widget = copy.deepcopy(self.data_widget)
        return obj


class ListWidget(BaseContainerWidget):
    template = "mongodbforms/list_widget.html"

    def render(self, name, value, attrs=None):
        if value is not None and not isinstance(value, (list, tuple)):
            raise TypeError(
                "Value supplied for %s must be a list or tuple." % name
            )

        output = []
        value = [] if value is None else value
        final_attrs = self.build_attrs(attrs)
        id_ = final_attrs.get('id', None)
        value.append('')
        for i, widget_value in enumerate(value):
            if id_:
                final_attrs = dict(final_attrs, id='%s_%s' % (id_, i))
            output.append(self.data_widget.render(
                name + '_%s' % i, widget_value, final_attrs)
            )
        return mark_safe(self.format_output(output))

    def format_output(self, rendered_widgets):
        """
        Given a list of rendered widgets (as strings), returns a Unicode string
        representing the HTML for the whole lot.

        This hook allows you to format the HTML design of the widgets, if
        needed.
        """
        return render_to_string(self.template, {"widgets": rendered_widgets})

    def value_from_datadict(self, data, files, name):
        widget = self.data_widget
        i = 0
        ret = []
        while (name + '_%s' % i) in data or (name + '_%s' % i) in files:
            value = widget.value_from_datadict(data, files, name + '_%s' % i)
            # we need a different list if we handle files. Basicly Django sends
            # back the initial values if we're not dealing with files. If we
            # store files on the list, we need to add empty values to the clean
            # data, so the list positions are kept.
            if value not in EMPTY_VALUES or (value is None and len(files) > 0):
                ret.append(value)
            i = i + 1
        return ret


class MapWidget(BaseContainerWidget):
    def __init__(self, data_widget, attrs=None):
        self.key_widget = TextInput()
        self.key_widget.is_localized = self.is_localized
        super(MapWidget, self).__init__(data_widget, attrs)

    def render(self, name, value, attrs=None):
        if value is not None and not isinstance(value, dict):
            raise TypeError("Value supplied for %s must be a dict." % name)

        output = []
        final_attrs = self.build_attrs(attrs)
        id_ = final_attrs.get('id', None)
        fieldset_attr = {}

        # in Python 3.X dict.items() returns dynamic *view objects*
        value = list(value.items())
        value.append(('', ''))
        for i, (key, widget_value) in enumerate(value):
            if id_:
                fieldset_attr = dict(
                    final_attrs, id='fieldset_%s_%s' % (id_, i)
                )
            group = []
            if not self.is_hidden:
                group.append(
                    mark_safe('<fieldset %s>' % flatatt(fieldset_attr)))

            if id_:
                final_attrs = dict(final_attrs, id='%s_key_%s' % (id_, i))
            group.append(self.key_widget.render(
                name + '_key_%s' % i, key, final_attrs)
            )

            if id_:
                final_attrs = dict(final_attrs, id='%s_value_%s' % (id_, i))
            group.append(self.data_widget.render(
                name + '_value_%s' % i, widget_value, final_attrs)
            )
            if not self.is_hidden:
                group.append(mark_safe('</fieldset>'))

            output.append(mark_safe(''.join(group)))
        return mark_safe(self.format_output(output))

    def value_from_datadict(self, data, files, name):
        i = 0
        ret = {}
        while (name + '_key_%s' % i) in data:
            key = self.key_widget.value_from_datadict(
                data, files, name + '_key_%s' % i
            )
            value = self.data_widget.value_from_datadict(
                data, files, name + '_value_%s' % i
            )
            if key not in EMPTY_VALUES:
                ret.update(((key, value), ))
            i = i + 1
        return ret

    def _get_media(self):
        """
        Media for a multiwidget is the combination of all media of
        the subwidgets.
        """
        media = super(MapWidget, self)._get_media()
        media = media + self.key_widget.media
        return media
    media = property(_get_media)

    def __deepcopy__(self, memo):
        obj = super(MapWidget, self).__deepcopy__(memo)
        obj.key_widget = copy.deepcopy(self.key_widget)
        return obj


class HiddenMapWidget(MapWidget):
    is_hidden = True

    def __init__(self, attrs=None):
        data_widget = HiddenInput()
        super(MapWidget, self).__init__(data_widget, attrs)
        self.key_widget = HiddenInput()


class DeletableFileWidget(MultiWidget):

    default_delete_label = "Delete this file."

    def __init__(self, file_widget=FileInput, attrs=None, delete_label=None):
        widgets = [file_widget, CheckboxInput]
        self.delete_label = delete_label or self.default_delete_label
        super(DeletableFileWidget, self).__init__(widgets, attrs)

    def decompress(self, value):
        return [value, False]

    def value_from_datadict(self, data, files, name):
        filename = name + '_0'
        if filename not in data and filename not in files:
            return None
        return super(DeletableFileWidget, self).value_from_datadict(data, files, name)

    def format_output(self, rendered_widgets):
        label = "<label>%s</label>" % self.delete_label
        return super(DeletableFileWidget, self).format_output(rendered_widgets) + label


class ListOfFilesWidget(ListWidget):
    template = "mongodbforms/list_of_files_widget.html"

    class Media:
        js = ('mongodbforms/list_of_files_widget.js', )

    def __init__(self, contained_widget=None, attrs=None, delete_label=None):
        super(ListOfFilesWidget, self).__init__(DeletableFileWidget(contained_widget, attrs, delete_label), attrs)

    def value_from_datadict(self, data, files, name):
        widget = self.data_widget
        i = 0
        ret = []
        value = widget.value_from_datadict(data, files, name + '_%s' % i)
        while value is not None:
            ret.append(value)
            i = i + 1
            value = widget.value_from_datadict(data, files, name + '_%s' % i)
        return ret
