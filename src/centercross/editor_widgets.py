from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtWidgets import QBoxLayout, QFormLayout, QScrollArea, QWidget, QTabWidget, QLayout


class ResponsivePanel(QWidget):
    """Keep every editor pane accessible at narrow viewport widths."""

    def __init__(self, columns, labels):
        super().__init__()
        self.setLayout(columns)
        self._columns = columns
        self._sizes = []
        for index in range(columns.count()):
            widget = columns.itemAt(index).widget()
            if widget:
                if columns.count()==3 and index==1:
                    widget.setMinimumWidth(360);widget.setMaximumWidth(460)
                self._sizes.append((widget, widget.minimumWidth(), widget.maximumWidth(), widget.minimumHeight()))
        self._scroll_sizes = [(s, s.minimumWidth(), s.maximumWidth(), s.minimumHeight())
                              for s in self.findChildren(QScrollArea)]
        self._labels=labels
        self._tabs=QTabWidget(self)
        self._tabs.setMinimumHeight(460)
        self._tab_index=0
        self._mode=None
        self._adapt(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adapt(event.size().width())

    def _adapt(self, width):
        mode="wide" if width>=(1500 if len(self._sizes)==3 else 1000) else "tabs"
        if mode == self._mode:
            return
        if self._mode=="tabs":self._tab_index=self._tabs.currentIndex()
        self._mode=mode
        compact=mode=="tabs"
        while self._columns.count():self._columns.takeAt(0)
        while self._tabs.count():self._tabs.removeTab(0)
        self._tabs.setVisible(compact)
        self._columns.setDirection(QBoxLayout.LeftToRight)
        for widget, minimum, maximum, height in self._sizes:
            widget.setParent(self)
            widget.setMinimumWidth(0 if compact else minimum)
            widget.setMaximumWidth(16777215 if compact else maximum)
            widget.setMinimumHeight(max(height, 240) if compact else height)
            if compact:self._tabs.addTab(widget,self._labels[self._tabs.count()])
            else:self._columns.addWidget(widget,1);widget.show()
        if compact:
            self._columns.addWidget(self._tabs,1)
            self._tabs.setCurrentIndex(max(0,min(self._tab_index,self._tabs.count()-1)))
        for scroll, minimum, maximum, height in self._scroll_sizes:
            scroll.setMinimumWidth(0 if compact else minimum)
            scroll.setMaximumWidth(16777215 if compact else maximum)
            scroll.setMinimumHeight(max(height, 420) if compact else height)


class ResponsiveScroll(QScrollArea):
    def __init__(self,page):
        super().__init__()
        self._page=page
        self._rows=[]
        for row in page.findChildren(QBoxLayout):
            if row.direction()==QBoxLayout.LeftToRight and not isinstance(row.parent(),ResponsivePanel):
                self._rows.append(row)
        self._pending=False
        page.installEventFilter(self)
        for widget in page.findChildren(QWidget):widget.installEventFilter(self)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(page)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._adapt_content()

    def eventFilter(self,obj,event):
        if event.type() in (QEvent.LayoutRequest,QEvent.Show) and not self._pending:
            self._pending=True;QTimer.singleShot(0,self._adapt_content)
        return super().eventFilter(obj,event)

    def _adapt_content(self):
        self._pending=False
        width=self.viewport().width()
        changed=False
        for row in self._rows:
            minimum=sum((max(row.itemAt(i).widget().minimumWidth(),row.itemAt(i).widget().minimumSizeHint().width()) if row.itemAt(i).widget() else row.itemAt(i).minimumSize().width()) for i in range(row.count()))+max(0,row.count()-1)*max(0,row.spacing())
            direction=QBoxLayout.TopToBottom if minimum>width-70 else QBoxLayout.LeftToRight
            if row.direction()!=direction:row.setDirection(direction);changed=True
        for form in self._page.findChildren(QFormLayout):
            policy=QFormLayout.WrapAllRows if width<650 else QFormLayout.WrapLongRows
            if form.rowWrapPolicy()!=policy:form.setRowWrapPolicy(policy);changed=True
        for panel in self._page.findChildren(ResponsivePanel):panel._adapt(width-10)
        if changed:
            # Hidden tab pages also contribute to the tab widget's minimum size.
            for layout in reversed(self._page.findChildren(QLayout)):layout.invalidate()
            self._page.layout().activate();self._page.updateGeometry()


def scroll_page(page,language="ko"):
    page.setObjectName("editorPage")
    layout = page.layout()
    # Editor workspaces are top-level rows consisting entirely of widgets.
    for index in range(layout.count()):
        item = layout.itemAt(index)
        row = item.layout()
        if isinstance(row, QBoxLayout) and row.count() >= 2 and all(
            row.itemAt(i).widget() is not None for i in range(row.count())
        ) and any(row.itemAt(i).widget().objectName() == "card" for i in range(row.count())):
            layout.takeAt(index)
            labels=(("Layers","Properties","Preview") if row.count()==3 else ("Settings","Preview")) if language=="en" else (("레이어","속성","미리보기") if row.count()==3 else ("설정","미리보기"))
            layout.insertWidget(index, ResponsivePanel(row,labels), 1)
    return ResponsiveScroll(page)
