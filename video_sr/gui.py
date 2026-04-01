from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import subprocess

from PySide6.QtCore import QPoint, QRect, Qt, QUrl, QObject, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from video_sr.backends import DEFAULT_ENGINE_PATH, BicubicBackend, build_backend, discover_models
from video_sr.pipeline import VideoJob, VideoSuperResolutionPipeline


class Worker(QObject):
    progress = Signal(int, int, str)
    log = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, job: VideoJob, backend_name: str, engine_path: str | None, model: str) -> None:
        super().__init__()
        self.job = job
        self.backend_name = backend_name
        self.engine_path = engine_path
        self.model = model

    def run(self) -> None:
        try:
            backend = build_backend(self.backend_name, engine_path=self.engine_path, model=self.model)
            pipeline = VideoSuperResolutionPipeline(
                backend=backend,
                progress_callback=self.progress.emit,
                log_callback=self.log.emit,
            )
            pipeline.run(self.job)
            self.finished.emit(str(self.job.output_path))
        except Exception as exc:
            self.failed.emit(str(exc))


class FrameCompareWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.before_pixmap: QPixmap | None = None
        self.after_pixmap: QPixmap | None = None
        self.split_ratio = 0.5
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_images(self, before_pixmap: QPixmap, after_pixmap: QPixmap) -> None:
        self.before_pixmap = before_pixmap
        self.after_pixmap = after_pixmap
        self.update()

    def clear_images(self) -> None:
        self.before_pixmap = None
        self.after_pixmap = None
        self.update()

    def export_comparison(self, output_path: Path) -> None:
        if self.before_pixmap is None or self.after_pixmap is None:
            raise RuntimeError("当前没有可导出的对比帧。")

        width = max(self.before_pixmap.width(), self.after_pixmap.width())
        height = max(self.before_pixmap.height(), self.after_pixmap.height())
        canvas = QImage(width, height, QImage.Format.Format_ARGB32)
        canvas.fill(QColor("#101010"))

        painter = QPainter(canvas)
        painter.drawPixmap(0, 0, self.before_pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        painter.setClipRect(QRect(0, 0, int(width * self.split_ratio), height))
        painter.drawPixmap(0, 0, self.after_pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        painter.setClipping(False)

        divider_x = int(width * self.split_ratio)
        painter.setPen(QPen(QColor("#f5f5f5"), 4))
        painter.drawLine(divider_x, 0, divider_x, height)

        painter.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        painter.fillRect(20, 20, 130, 42, QColor(0, 0, 0, 150))
        painter.fillRect(width - 150, 20, 130, 42, QColor(0, 0, 0, 150))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRect(20, 20, 130, 42), Qt.AlignmentFlag.AlignCenter, "Before")
        painter.drawText(QRect(width - 150, 20, 130, 42), Qt.AlignmentFlag.AlignCenter, "After")
        painter.end()

        if not canvas.save(str(output_path)):
            raise RuntimeError(f"无法保存截图到 {output_path}")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._update_split_ratio(event.position().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_split_ratio(event.position().toPoint())

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#121212"))

        if self.before_pixmap is None or self.after_pixmap is None:
            painter.setPen(QColor("#d0d0d0"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂停后可在这里拖动滑块比较当前帧")
            painter.end()
            return

        target = self._target_rect()
        before_scaled = self.before_pixmap.scaled(target.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        after_scaled = self.after_pixmap.scaled(target.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        draw_rect = QRect(
            target.x() + (target.width() - before_scaled.width()) // 2,
            target.y() + (target.height() - before_scaled.height()) // 2,
            before_scaled.width(),
            before_scaled.height(),
        )

        painter.drawPixmap(draw_rect, before_scaled)
        clip_rect = QRect(draw_rect.x(), draw_rect.y(), int(draw_rect.width() * self.split_ratio), draw_rect.height())
        painter.setClipRect(clip_rect)
        painter.drawPixmap(draw_rect, after_scaled)
        painter.setClipping(False)

        divider_x = draw_rect.x() + int(draw_rect.width() * self.split_ratio)
        painter.setPen(QPen(QColor("#f5f5f5"), 3))
        painter.drawLine(divider_x, draw_rect.y(), divider_x, draw_rect.bottom())

        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.fillRect(draw_rect.x() + 16, draw_rect.y() + 16, 90, 32, QColor(0, 0, 0, 150))
        painter.fillRect(draw_rect.right() - 106, draw_rect.y() + 16, 90, 32, QColor(0, 0, 0, 150))
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRect(draw_rect.x() + 16, draw_rect.y() + 16, 90, 32), Qt.AlignmentFlag.AlignCenter, "Before")
        painter.drawText(QRect(draw_rect.right() - 106, draw_rect.y() + 16, 90, 32), Qt.AlignmentFlag.AlignCenter, "After")
        painter.end()

    def _target_rect(self) -> QRect:
        return self.rect().adjusted(12, 12, -12, -12)

    def _update_split_ratio(self, point: QPoint) -> None:
        target = self._target_rect()
        if target.width() <= 0:
            return
        ratio = (point.x() - target.x()) / target.width()
        self.split_ratio = max(0.0, min(1.0, ratio))
        self.update()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.compare_video_path: Path | None = None
        self.compare_fps = 24.0
        self.frame_cache_dir = Path(tempfile.gettempdir()) / "video_sr_frame_cache"
        self.frame_cache_dir.mkdir(parents=True, exist_ok=True)
        self.setWindowTitle("Video Super Resolution")
        self.resize(1320, 920)
        self._build_ui()
        self._connect_signals()
        self._load_defaults()

    def _build_ui(self) -> None:
        root = QWidget()
        outer_layout = QVBoxLayout(root)
        outer_layout.setSpacing(14)

        header = QLabel("视频超分辨率桌面工具")
        header.setStyleSheet("font-size: 24px; font-weight: 700;")
        subtitle = QLabel("生成超分视频后，可一键创建左右拼接的对比预览，并支持逐帧暂停和拖动滑块比较。")
        subtitle.setStyleSheet("color: #555;")
        outer_layout.addWidget(header)
        outer_layout.addWidget(subtitle)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(14)
        outer_layout.addLayout(content_layout, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(14)

        paths_group = QGroupBox("文件")
        paths_layout = QGridLayout(paths_group)
        self.input_edit = QLineEdit()
        self.output_edit = QLineEdit()
        self.engine_edit = QLineEdit()
        self.input_button = QPushButton("选择输入")
        self.output_button = QPushButton("选择输出")
        self.engine_button = QPushButton("选择引擎")
        paths_layout.addWidget(QLabel("输入视频"), 0, 0)
        paths_layout.addWidget(self.input_edit, 0, 1)
        paths_layout.addWidget(self.input_button, 0, 2)
        paths_layout.addWidget(QLabel("输出视频"), 1, 0)
        paths_layout.addWidget(self.output_edit, 1, 1)
        paths_layout.addWidget(self.output_button, 1, 2)
        paths_layout.addWidget(QLabel("引擎路径"), 2, 0)
        paths_layout.addWidget(self.engine_edit, 2, 1)
        paths_layout.addWidget(self.engine_button, 2, 2)
        left_layout.addWidget(paths_group)

        options_group = QGroupBox("处理参数")
        options_layout = QFormLayout(options_group)
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["bicubic", "realesrgan-ncnn-vulkan"])
        self.model_combo = QComboBox()
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(2, 4)
        self.scale_spin.setValue(2)
        self.keep_audio_checkbox = QCheckBox("保留原视频音频")
        self.keep_audio_checkbox.setChecked(True)
        options_layout.addRow("超分后端", self.backend_combo)
        options_layout.addRow("模型", self.model_combo)
        options_layout.addRow("放大倍数", self.scale_spin)
        options_layout.addRow("音频", self.keep_audio_checkbox)
        left_layout.addWidget(options_group)

        progress_group = QGroupBox("处理状态")
        progress_layout = QVBoxLayout(progress_group)
        self.status_label = QLabel("等待开始")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.log_edit)
        left_layout.addWidget(progress_group, 1)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.refresh_models_button = QPushButton("刷新模型")
        buttons.addWidget(self.refresh_models_button)
        buttons.addStretch(1)
        buttons.addWidget(self.start_button)
        left_layout.addLayout(buttons)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(14)

        source_group = QGroupBox("源文件")
        source_layout = QVBoxLayout(source_group)
        self.before_label = QLabel("原视频：未加载")
        self.after_label = QLabel("超分视频：未生成")
        source_layout.addWidget(self.before_label)
        source_layout.addWidget(self.after_label)
        open_buttons = QHBoxLayout()
        self.open_before_button = QPushButton("打开原视频")
        self.open_after_button = QPushButton("打开输出视频")
        self.make_compare_button = QPushButton("生成对比预览")
        open_buttons.addWidget(self.open_before_button)
        open_buttons.addWidget(self.open_after_button)
        open_buttons.addWidget(self.make_compare_button)
        source_layout.addLayout(open_buttons)
        right_layout.addWidget(source_group)

        preview_group = QGroupBox("对比视频预览")
        preview_layout = QVBoxLayout(preview_group)
        self.compare_label = QLabel("对比视频：未生成")
        self.frame_label = QLabel("帧信息：--")
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(700, 380)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        preview_controls = QHBoxLayout()
        self.play_button = QPushButton("播放")
        self.pause_button = QPushButton("暂停")
        self.prev_frame_button = QPushButton("上一帧")
        self.next_frame_button = QPushButton("下一帧")
        preview_controls.addStretch(1)
        preview_controls.addWidget(self.prev_frame_button)
        preview_controls.addWidget(self.next_frame_button)
        preview_controls.addWidget(self.play_button)
        preview_controls.addWidget(self.pause_button)
        preview_layout.addWidget(self.compare_label)
        preview_layout.addWidget(self.frame_label)
        preview_layout.addWidget(self.video_widget, 1)
        preview_layout.addWidget(self.position_slider)
        preview_layout.addLayout(preview_controls)
        right_layout.addWidget(preview_group, 5)

        frame_group = QGroupBox("当前帧滑块对比")
        frame_layout = QVBoxLayout(frame_group)
        frame_tip = QLabel("暂停后点击“刷新当前帧”，或直接用上一帧/下一帧逐帧比较。拖动中线可查看局部差异。")
        frame_tip.setStyleSheet("color: #555;")
        self.frame_compare_widget = FrameCompareWidget()
        frame_buttons = QHBoxLayout()
        self.refresh_frame_button = QPushButton("刷新当前帧")
        self.export_frame_button = QPushButton("导出当前帧对比截图")
        frame_buttons.addWidget(self.refresh_frame_button)
        frame_buttons.addWidget(self.export_frame_button)
        frame_buttons.addStretch(1)
        frame_layout.addWidget(frame_tip)
        frame_layout.addWidget(self.frame_compare_widget, 1)
        frame_layout.addLayout(frame_buttons)
        right_layout.addWidget(frame_group, 4)

        content_layout.addWidget(left_panel, 5)
        content_layout.addWidget(right_panel, 7)

        self.audio_output = QAudioOutput(self)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.input_button.clicked.connect(self._choose_input)
        self.output_button.clicked.connect(self._choose_output)
        self.engine_button.clicked.connect(self._choose_engine)
        self.start_button.clicked.connect(self._start_processing)
        self.refresh_models_button.clicked.connect(self._refresh_models)
        self.open_before_button.clicked.connect(self._choose_before_video)
        self.open_after_button.clicked.connect(self._choose_after_video)
        self.make_compare_button.clicked.connect(self._make_compare_preview)
        self.play_button.clicked.connect(self.media_player.play)
        self.pause_button.clicked.connect(self._pause_preview)
        self.prev_frame_button.clicked.connect(lambda: self._step_frame(-1))
        self.next_frame_button.clicked.connect(lambda: self._step_frame(1))
        self.refresh_frame_button.clicked.connect(self._refresh_current_frame_compare)
        self.export_frame_button.clicked.connect(self._export_current_frame_compare)
        self.backend_combo.currentTextChanged.connect(self._update_backend_state)
        self.scale_spin.valueChanged.connect(self._sync_model_for_scale)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.position_slider.sliderMoved.connect(self.media_player.setPosition)

    def _load_defaults(self) -> None:
        if DEFAULT_ENGINE_PATH.exists():
            self.engine_edit.setText(str(DEFAULT_ENGINE_PATH))
        self._refresh_models()
        self._update_backend_state()
        self.play_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.prev_frame_button.setEnabled(False)
        self.next_frame_button.setEnabled(False)
        self.refresh_frame_button.setEnabled(False)
        self.export_frame_button.setEnabled(False)

    def _choose_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择输入视频", "", "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv)")
        if not path:
            return
        self.input_edit.setText(path)
        self.before_label.setText(f"原视频：{path}")
        if not self.output_edit.text():
            input_path = Path(path)
            output_path = input_path.with_name(f"{input_path.stem}_upscaled.mp4")
            self.output_edit.setText(str(output_path))

    def _choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "选择输出视频", "output.mp4", "MP4 视频 (*.mp4)")
        if path:
            self.output_edit.setText(path)

    def _choose_engine(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 Real-ESRGAN 引擎", self.engine_edit.text(), "可执行文件 (*.exe)")
        if path:
            self.engine_edit.setText(path)
            self._refresh_models()

    def _choose_before_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择原视频", self.input_edit.text(), "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv)")
        if path:
            self.input_edit.setText(path)
            self.before_label.setText(f"原视频：{path}")

    def _choose_after_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择输出视频", self.output_edit.text() or self.input_edit.text(), "视频文件 (*.mp4 *.mov *.mkv *.avi *.flv)")
        if path:
            self.output_edit.setText(path)
            self.after_label.setText(f"超分视频：{path}")

    def _refresh_models(self) -> None:
        engine_path = self.engine_edit.text().strip() or None
        models = discover_models(engine_path)
        current_model = self.model_combo.currentText()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
        else:
            self.model_combo.addItems(["realesr-animevideov3", "realesrgan-x4plus", "realesrgan-x4plus-anime"])
        if current_model:
            index = self.model_combo.findText(current_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)
        self._sync_model_for_scale()

    def _sync_model_for_scale(self) -> None:
        current_model = self.model_combo.currentText()
        scale = self.scale_spin.value()
        if current_model.startswith("realesrgan-x4plus") and scale != 4:
            self.status_label.setText("x4plus 系列模型仅支持 4 倍")
        elif current_model == "realesr-animevideov3":
            self.status_label.setText(f"将自动选择 animevideov3 的 x{scale} 模型")
        else:
            self.status_label.setText("等待开始")

    def _update_backend_state(self) -> None:
        using_ai = self.backend_combo.currentText() == "realesrgan-ncnn-vulkan"
        self.engine_edit.setEnabled(using_ai)
        self.engine_button.setEnabled(using_ai)
        self.model_combo.setEnabled(using_ai)
        self.refresh_models_button.setEnabled(using_ai)

    def _start_processing(self) -> None:
        if self.thread is not None:
            QMessageBox.warning(self, "正在处理", "当前已有任务在运行，请等待完成。")
            return

        input_text = self.input_edit.text().strip()
        output_text = self.output_edit.text().strip()
        if not input_text or not Path(input_text).exists():
            QMessageBox.critical(self, "输入无效", "请选择存在的输入视频文件。")
            return
        if not output_text:
            QMessageBox.critical(self, "输出无效", "请选择输出视频路径。")
            return

        backend_name = self.backend_combo.currentText()
        scale = self.scale_spin.value()
        model = self.model_combo.currentText()
        engine_path = self.engine_edit.text().strip() or None

        if backend_name == "realesrgan-ncnn-vulkan" and not engine_path:
            QMessageBox.critical(self, "缺少引擎", "请选择 realesrgan-ncnn-vulkan.exe 的路径。")
            return

        job = VideoJob(
            input_path=Path(input_text).expanduser().resolve(),
            output_path=Path(output_text).expanduser().resolve(),
            scale=scale,
            keep_audio=self.keep_audio_checkbox.isChecked(),
        )

        self.media_player.stop()
        self.compare_video_path = None
        self.compare_label.setText("对比视频：未生成")
        self.frame_label.setText("帧信息：--")
        self.frame_compare_widget.clear_images()
        self.after_label.setText("超分视频：处理中")
        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self.position_slider.setValue(0)
        self.start_button.setEnabled(False)
        self.status_label.setText("准备开始")

        self.thread = QThread(self)
        self.worker = Worker(job, backend_name, engine_path, model)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.start()

    def _make_compare_preview(self) -> None:
        input_path = Path(self.input_edit.text().strip())
        output_path = Path(self.output_edit.text().strip())
        if not input_path.exists() or not output_path.exists():
            QMessageBox.critical(self, "缺少视频", "请先准备好原视频和超分后视频。")
            return

        try:
            pipeline = VideoSuperResolutionPipeline(BicubicBackend())
            compare_path = output_path.with_name(f"{output_path.stem}_compare.mp4")
            command = [
                str(pipeline.ffmpeg_path),
                "-y",
                "-i",
                str(input_path),
                "-i",
                str(output_path),
                "-filter_complex",
                "[0:v][1:v]scale2ref=flags=lanczos[before][after];[before][after]hstack=inputs=2[v];[v]drawbox=x=iw/2-2:y=0:w=4:h=ih:color=white@0.9:t=fill[vout]",
                "-map",
                "[vout]",
                "-map",
                "1:a?",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(compare_path),
            ]
            self.status_label.setText("正在生成对比预览")
            self.log_edit.appendPlainText("正在生成左右拼接的对比视频...")
            subprocess.run(command, check=True, env=pipeline.process_env)
            self.compare_video_path = compare_path
            self.compare_fps = self._probe_fps(compare_path)
            self._load_compare_preview(compare_path)
            self.status_label.setText("对比预览已生成")
            self.log_edit.appendPlainText(f"对比视频已生成: {compare_path}")
            self._refresh_current_frame_compare()
        except Exception as exc:
            QMessageBox.critical(self, "生成失败", str(exc))
            self.log_edit.appendPlainText(f"生成对比预览失败: {exc}")

    def _append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)

    def _update_progress(self, current: int, total: int, message: str) -> None:
        percent = 0 if total == 0 else int(current * 100 / total)
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _on_finished(self, output_path: str) -> None:
        self.progress_bar.setValue(100)
        self.status_label.setText("处理完成")
        self.output_edit.setText(output_path)
        self.after_label.setText(f"超分视频：{output_path}")
        self.log_edit.appendPlainText(f"输出文件: {output_path}")
        QMessageBox.information(self, "完成", f"视频已生成:\n{output_path}\n\n现在可以点击“生成对比预览”来播放单轨对比视频。")

    def _on_failed(self, error: str) -> None:
        self.status_label.setText("处理失败")
        self.log_edit.appendPlainText(f"错误: {error}")
        QMessageBox.critical(self, "处理失败", error)

    def _cleanup_thread(self) -> None:
        self.start_button.setEnabled(True)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        if self.thread is not None:
            self.thread.deleteLater()
            self.thread = None

    def _load_compare_preview(self, path: Path) -> None:
        self.compare_label.setText(f"对比视频：{path}")
        self.media_player.setSource(QUrl.fromLocalFile(str(path)))
        self.play_button.setEnabled(True)
        self.pause_button.setEnabled(True)
        self.prev_frame_button.setEnabled(True)
        self.next_frame_button.setEnabled(True)
        self.refresh_frame_button.setEnabled(True)
        self.export_frame_button.setEnabled(True)
        self.media_player.play()

    def _pause_preview(self) -> None:
        self.media_player.pause()
        self._refresh_current_frame_compare()

    def _step_frame(self, direction: int) -> None:
        if self.compare_video_path is None:
            return
        self.media_player.pause()
        frame_duration = max(int(round(1000 / max(self.compare_fps, 0.001))), 1)
        current = self.media_player.position()
        target = max(current + direction * frame_duration, 0)
        if self.media_player.duration() > 0:
            target = min(target, self.media_player.duration())
        self.media_player.setPosition(target)
        self._update_frame_label(target)
        self._refresh_current_frame_compare()

    def _refresh_current_frame_compare(self) -> None:
        input_path = Path(self.input_edit.text().strip())
        output_path = Path(self.output_edit.text().strip())
        if not input_path.exists() or not output_path.exists():
            return

        try:
            timestamp = self.media_player.position() / 1000.0
            before_frame = self.frame_cache_dir / "before_frame.png"
            after_frame = self.frame_cache_dir / "after_frame.png"
            self._extract_frame(input_path, timestamp, before_frame)
            self._extract_frame(output_path, timestamp, after_frame)
            before_pixmap = QPixmap(str(before_frame))
            after_pixmap = QPixmap(str(after_frame))
            if before_pixmap.isNull() or after_pixmap.isNull():
                raise RuntimeError("帧提取成功，但图片加载失败。")
            self.frame_compare_widget.set_images(before_pixmap, after_pixmap)
            self._update_frame_label(self.media_player.position())
        except Exception as exc:
            self.log_edit.appendPlainText(f"刷新当前帧失败: {exc}")

    def _export_current_frame_compare(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出当前帧对比截图", "frame_compare.png", "PNG 图片 (*.png)")
        if not path:
            return
        try:
            self.frame_compare_widget.export_comparison(Path(path))
            self.log_edit.appendPlainText(f"当前帧对比截图已导出: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _on_position_changed(self, position: int) -> None:
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(position)
        self.position_slider.blockSignals(False)
        self._update_frame_label(position)

    def _on_duration_changed(self, duration: int) -> None:
        self.position_slider.setRange(0, max(duration, 0))

    def _update_frame_label(self, position_ms: int) -> None:
        frame_number = int(round((position_ms / 1000.0) * self.compare_fps))
        self.frame_label.setText(f"帧信息：第 {frame_number} 帧 | {position_ms} ms | {self.compare_fps:.3f} fps")

    def _extract_frame(self, video_path: Path, timestamp: float, target_path: Path) -> None:
        pipeline = VideoSuperResolutionPipeline(BicubicBackend())
        command = [
            str(pipeline.ffmpeg_path),
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(target_path),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True, env=pipeline.process_env)

    def _probe_fps(self, video_path: Path) -> float:
        pipeline = VideoSuperResolutionPipeline(BicubicBackend())
        command = [
            str(pipeline.ffprobe_path),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env=pipeline.process_env)
        rate = result.stdout.strip()
        if "/" in rate:
            numerator, denominator = rate.split("/", maxsplit=1)
            return float(numerator) / float(denominator)
        return float(rate)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
