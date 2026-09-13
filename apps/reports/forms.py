# -*- coding: utf-8 -*-
"""Формы раздела «Суточные рапорты».

Проверки здесь устроены от дешёвых к дорогим: сначала имя и размер,
потом сигнатура файла, и только потом попытка открыть его как книгу
Excel. Так на заведомо неподходящий файл не тратится время разбора,
а пользователь получает внятный ответ сразу.

Все сообщения обращены к тому, кто загружает рапорт каждое утро,
а не к разработчику: они говорят, что не так и что сделать.
"""
from __future__ import annotations

import zipfile

from django import forms
from django.conf import settings
from django.template.defaultfilters import filesizeformat
from django.utils import timezone

from .loader import digest
from .models import Upload

#: Первые байты книги Excel: это zip-архив.
ZIP_SIGNATURE = b"PK\x03\x04"

#: Лист, на котором лежит суточный рапорт. Если его нет, книга,
#: скорее всего, не та — но разбор умеет искать лист и по содержимому,
#: поэтому проверка нестрогая и служит подсказкой.
SHEET_HINT = "Сут.рапорт"


class UploadForm(forms.Form):
    """Загрузка суточного рапорта."""

    file = forms.FileField(
        label="Файл суточного рапорта",
        help_text=("Книга Excel в формате .xlsx, не больше "
                   f"{settings.MAX_UPLOAD_SIZE_MB} МБ"),
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
        error_messages={
            "required": "Выберите файл суточного рапорта.",
            "empty": "Файл пустой — похоже, он не докачался.",
        })

    note = forms.CharField(
        label="Пояснение", required=False, max_length=300,
        widget=forms.TextInput(attrs={
            "placeholder": "например: повторная загрузка, "
                           "исправлены данные по ППД"}),
        help_text="Нужно, если вы загружаете рапорт за дату повторно.")

    def clean_file(self):
        """Проверить файл до того, как он попадёт в разбор.

        Returns:
            Загруженный файл, если он пригоден.

        Raises:
            ValidationError: С объяснением, что именно не так.
        """
        uploaded = self.cleaned_data["file"]

        self._check_name(uploaded.name)
        self._check_size(uploaded.size)
        self._check_signature(uploaded)
        self._check_workbook(uploaded)
        return uploaded

    def _check_name(self, name: str) -> None:
        """Расширение должно быть .xlsx.

        Raises:
            ValidationError: Если расширение другое.
        """
        lowered = name.lower()
        if lowered.endswith(".xls"):
            raise forms.ValidationError(
                "Это старый формат Excel (.xls). Откройте файл в Excel "
                "и сохраните как «Книга Excel (*.xlsx)».")
        if not lowered.endswith(".xlsx"):
            raise forms.ValidationError(
                "Суточный рапорт — это книга Excel с расширением .xlsx. "
                "Выбран файл «%(name)s».", params={"name": name})

    def _check_size(self, size: int) -> None:
        """Размер должен быть правдоподобным.

        Raises:
            ValidationError: Если файл пуст или слишком велик.
        """
        if not size:
            raise forms.ValidationError(
                "Файл пустой — похоже, он не докачался.")

        limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if size > limit:
            raise forms.ValidationError(
                "Файл весит %(size)s, а допустимо не больше %(limit)s. "
                "Суточный рапорт обычно занимает около 300 КБ — "
                "проверьте, что выбран нужный файл.",
                params={"size": filesizeformat(size),
                        "limit": filesizeformat(limit)})

    def _check_signature(self, uploaded) -> None:
        """Файл должен начинаться как zip-архив.

        Книга .xlsx — это zip. Проверка отсекает переименованные файлы
        до того, как их попытается открыть разборщик.

        Raises:
            ValidationError: Если сигнатура не совпала.
        """
        uploaded.seek(0)
        head = uploaded.read(len(ZIP_SIGNATURE))
        uploaded.seek(0)
        if head != ZIP_SIGNATURE:
            raise forms.ValidationError(
                "Файл не похож на книгу Excel: у него другое содержимое. "
                "Возможно, ему просто переименовали расширение.")

    def _check_workbook(self, uploaded) -> None:
        """Книга должна открываться и содержать листы.

        Raises:
            ValidationError: Если архив повреждён или пуст.
        """
        uploaded.seek(0)
        try:
            with zipfile.ZipFile(uploaded) as book:
                broken = book.testzip()
                names = book.namelist()
        except zipfile.BadZipFile:
            raise forms.ValidationError(
                "Книга Excel повреждена и не открывается. Попробуйте "
                "открыть её в Excel и сохранить заново.") from None
        finally:
            uploaded.seek(0)

        if broken is not None:
            raise forms.ValidationError(
                "Книга Excel повреждена: не читается её часть «%(part)s».",
                params={"part": broken})
        if not any(name.startswith("xl/") for name in names):
            raise forms.ValidationError(
                "Это архив, но не книга Excel. Выберите файл суточного "
                "рапорта.")

    def clean(self):
        """Предупредить о повторной загрузке того же самого файла.

        Загрузка идемпотентна, поэтому повтор не опасен. Но чаще всего
        он означает, что человек ошибся файлом, и сказать об этом стоит.
        """
        cleaned = super().clean()
        uploaded = cleaned.get("file")
        if uploaded is None:
            return cleaned

        uploaded.seek(0)
        checksum = digest(uploaded)
        uploaded.seek(0)
        cleaned["sha256"] = checksum

        same = (Upload.objects
                .filter(sha256=checksum, status=Upload.Status.LOADED)
                .select_related("report").order_by("-uploaded_at").first())
        if same is not None and not cleaned.get("note"):
            when = timezone.localtime(same.uploaded_at).strftime(
                "%d.%m.%Y в %H:%M")
            date = (f" за {same.report.date:%d.%m.%Y}"
                    if same.report_id else "")
            self.add_error(
                "file",
                forms.ValidationError(
                    "Ровно этот файл уже загружали %(when)s%(date)s. "
                    "Если загружаете намеренно, напишите пояснение — "
                    "оно останется в истории загрузок.",
                    params={"when": when, "date": date}))
        return cleaned
