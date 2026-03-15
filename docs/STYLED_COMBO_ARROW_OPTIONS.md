# StyledComboBox の ∨ が表示されない原因候補と修正方針

## 現状
- **プロパティ**の作者・シリーズ・キャラ・タグ: `_DropdownEntry` = QLineEdit + **QPushButton("∨")** → ∨ は表示される
- **サイドバー**のコンボ: `StyledComboBox`（QComboBox 継承）で paintEvent や子 QLabel("∨") を試したが **表示されない**

---

## 可能性の洗い出し

### A. QComboBox の内部構造・スタック順
1. **スタイルが内部で「ドロップダウン用ウィジェット」を持っている**  
   QComboBox のスタイル実装が、ドロップダウン領域に別の QWidget を置いている場合、その子が常に手前に描画され、こちらの子 QLabel や paintEvent が隠れる可能性がある。
2. **子ウィジェットの Z-order**  
   `raise_()` を resizeEvent で呼んでも、その後にスタイル側が再描画や子の追加で前面に持ってくる可能性がある。

### B. クリッピング
3. **QComboBox が content rect でクリップしている**  
   コンボが「テキスト領域」と「ドロップダウン領域」で描画を分けており、子ウィジェットもドロップダウン側がクリップされて見えなくなっている可能性。
4. **::drop-down を width: 0 にした影響**  
   スタイルが「ドロップダウン領域」を幅 0 と解釈し、その分だけ右端をクリップしている可能性。

### C. タイミング・レイアウト
5. **resizeEvent の呼ばれ方**  
   初回表示時に resizeEvent が呼ばれていない、または width/height が 0 のまま setGeometry している可能性。
6. **サイドバーのレイアウト**  
   コンボが layout に add されたあと、実際の幅が確定する前に _arrow の geometry が設定されている可能性。

### D. 根本方針のずれ
7. **QComboBox の「上に乗せる」前提が成立していない**  
   QComboBox はスタイルが強く、内部でサブコントロールを描画するため、「コンボの子として矢印を乗せる」方式がそもそもそのスタイルでは許されていない可能性がある。

---

## 修正方針の候補

### 方針1: コンボを包むコンテナで「外から」矢印を重ねる（プロパティと同構造）
- **内容**: `_DropdownEntry` と同様に、**QComboBox の親**を「コンテナ QWidget」にし、そのコンテナの子として「QComboBox」と「QLabel("∨")」を並べる。矢印はコンボの**兄弟**なので、スタイルの描画に隠されない。
- **変更**: サイドバーで `StyledComboBox` の代わりに、`SidebarComboWidget(QWidget)` を用意し、その中に通常の `QComboBox` + 右端に `QLabel("∨")` を配置。コンボには `padding-right` で矢印分の余白を確保。
- **メリット**: プロパティで実績のある「入力＋矢印を横に並べる」構造に寄せられる。  
- **デメリット**: サイドバー側のコード変更がやや多くなる。

#### SidebarComboWidget のコード例（theme.py）

```python
from PySide6.QtWidgets import QWidget, QComboBox as _QComboBox, QLabel
from PySide6.QtCore import Qt

class SidebarComboWidget(QWidget):
    """コンボと∨を兄弟で並べるコンテナ。矢印はコンテナの子なので表示される。"""
    _ARROW_WIDTH = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self._combo = _QComboBox(self)
        self._combo.setStyleSheet("""
            QComboBox::drop-down { width: 0; border: none; background: transparent; }
            QComboBox { padding-right: 28px; }
        """)
        self._arrow = QLabel("∨", self)
        self._arrow.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._arrow.setStyleSheet("background: transparent; color: #CCCCCC; font-size: 13px;")
        self._arrow.setAlignment(Qt.AlignCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self._combo.setGeometry(0, 0, w, h)
        self._arrow.setGeometry(w - self._ARROW_WIDTH, 0, self._ARROW_WIDTH, h)
        self._arrow.raise_()

    # QComboBox API の転送
    def addItem(self, text: str, userData=None): return self._combo.addItem(text, userData)
    def model(self): return self._combo.model()
    def setCurrentIndex(self, index: int): return self._combo.setCurrentIndex(index)
    def currentIndex(self) -> int: return self._combo.currentIndex()
    def currentIndexChanged(self): return self._combo.currentIndexChanged
    def itemData(self, index: int): return self._combo.itemData(index)
    def count(self) -> int: return self._combo.count()
    def blockSignals(self, block: bool) -> bool: return self._combo.blockSignals(block)
```

サイドバーでの利用（sidebar.py）:

```python
from theme import THEME_COLORS, SidebarComboWidget

# モード選択
self._combo = SidebarComboWidget()
self._combo.setFixedHeight(32)
self._combo.addItem("───", "none")
self._combo.model().item(0).setSizeHint(QSize(0, 0))
# ... addItem / setCurrentIndex / currentIndexChanged などは従来どおり self._combo で利用
layout.addWidget(self._combo)
```

### 方針2: グローバル QSS の ::down-arrow で矢印を出す（サブクラス廃止）
- **内容**: StyledComboBox をやめ、通常の QComboBox のみ使う。`::down-arrow` に **画像（∨ を描いた小画像）** を指定する。Qt の QSS では `image: url(...)` で画像を指定できる。
- **変更**: theme.py で `QComboBox::down-arrow` に `image: url(chevron_down.png)` などを指定。小さな ∨ の PNG をリソースに持つか、起動時に QImage で描画して一時ファイル化するなど。
- **メリット**: すべての QComboBox（サイドバー・フィルター・設定など）で同じ矢印になる。  
- **デメリット**: 画像の用意・管理が必要。画像なしだと従来どおり「矢印なし」のまま。

### 方針3: QProxyStyle でコンボの描画だけオーバーライド
- **内容**: アプリで QProxyStyle を用意し、`drawComplexControl(CC_ComboBox, ...)` のときだけドロップダウン領域に ∨ を描画する。スタイルの描画パイプラインに乗せる。
- **メリット**: QComboBox を継承せず、すべてのコンボに一括で適用できる。  
- **デメリット**: 実装とデバッグが重い。QStyle のオプションや状態の扱いを把握する必要がある。

### 方針4: デバッグで「今どこで潰れているか」を特定する
- **内容**: 次のような確認を行う。  
  - StyledComboBox の子 QLabel に `setStyleSheet("background: red;")` を付けて、**四角がコンボの右端に見えるか**を確認。  
  - 見える → テキスト "∨" やフォント・色の問題。見えない → クリップ・Z-order・親の描画で隠れている。
- **メリット**: 原因が「描画順・クリップ」か「テキスト・スタイル」かに切り分けできる。  
- **デメリット**: あくまで調査用。根本修正は上記いずれかの方針で行う必要がある。

### 方針5: 矢印を諦めてデフォルトの三角にする
- **内容**: グローバル QSS の `QComboBox::down-arrow` で、`image: none` をやめ、Qt のデフォルト矢印（border で作った三角など）が使われるようにする。または `width/height` を 0 にせず、何らかの画像を指定する。
- **メリット**: 実装が軽い。  
- **デメリット**: 「∨ に統一したい」という要望とはずれる可能性がある。

---

## 推奨の進め方
1. **まず方針4**で、子 QLabel を `background: red` にしたときに四角が見えるか確認する。  
2. **四角が見える** → フォント・文字色・"∨" の文字コードを確認。  
3. **四角も見えない** → QComboBox の子では描画が隠れていると判断し、**方針1（コンテナ + コンボと矢印を兄弟で並べる）** に切り替えるのが確実。
