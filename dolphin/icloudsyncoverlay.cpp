// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Antonio Rosario Intilisano (InTiLinuX)
//
// Overlay icons for the folder kept in sync by icloud-sync.
//
// After every successful sync the daemon writes ~/.local/state/icloud-sync/overlay-state.tsv with
// what was just synced: path, size and modification time in milliseconds. A file that still matches
// that record is in sync; anything else under the root is waiting for the next sync.

#include <KOverlayIconPlugin>

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QHash>
#include <QSet>
#include <QTimeZone>
#include <QUrl>

class ICloudSyncOverlay : public KOverlayIconPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID "org.kde.overlayicon.icloudsync" FILE "icloudsyncoverlay.json")

public:
    ICloudSyncOverlay();
    QStringList getOverlays(const QUrl &url) override;

private:
    struct Known {
        qint64 size;
        qint64 mtimeMs;
    };

    bool load();
    void stateDirChanged();
    QStringList overlaysFor(const QString &path) const;

    QString m_stateDir;
    QString m_stateFile;
    QString m_root; // with a trailing slash; empty until a state file has been read
    QHash<QString, Known> m_files;
    QSet<QString> m_dirs;
    QStringList m_exclude;
    QDateTime m_loaded;
    QSet<QUrl> m_shown; // items Dolphin asked about, to refresh them after the next sync
    QFileSystemWatcher m_watcher;
};

ICloudSyncOverlay::ICloudSyncOverlay()
{
    QString base = qEnvironmentVariable("XDG_STATE_HOME");
    if (base.isEmpty()) {
        base = QDir::homePath() + QStringLiteral("/.local/state");
    }
    m_stateDir = base + QStringLiteral("/icloud-sync");
    m_stateFile = m_stateDir + QStringLiteral("/overlay-state.tsv");
    connect(&m_watcher, &QFileSystemWatcher::directoryChanged, this, &ICloudSyncOverlay::stateDirChanged);
    load();
}

bool ICloudSyncOverlay::load()
{
    // The daemon replaces the file with a rename, so the directory is what has to be watched.
    if (m_watcher.directories().isEmpty() && QFileInfo(m_stateDir).isDir()) {
        m_watcher.addPath(m_stateDir);
    }
    QFile file(m_stateFile);
    const QDateTime written = QFileInfo(m_stateFile).lastModified();
    if (!written.isValid() || written == m_loaded || !file.open(QIODevice::ReadOnly)) {
        return false;
    }
    m_loaded = written;
    m_root.clear();
    m_files.clear();
    m_dirs.clear();
    m_exclude.clear();
    while (!file.atEnd()) {
        QByteArray line = file.readLine();
        if (line.endsWith('\n')) {
            line.chop(1);
        }
        const QList<QByteArray> parts = line.split('\t');
        if (parts.size() < 2) {
            continue;
        }
        const QByteArray kind = parts.at(0);
        if (kind == "root") {
            m_root = QString::fromUtf8(parts.at(1)) + QLatin1Char('/');
        } else if (kind == "exclude") {
            m_exclude.append(QString::fromUtf8(parts.at(1)));
        } else if (kind == "d") {
            m_dirs.insert(QString::fromUtf8(parts.at(1)));
        } else if (kind == "f" && parts.size() == 4) {
            m_files.insert(QString::fromUtf8(parts.at(3)), Known{parts.at(1).toLongLong(), parts.at(2).toLongLong()});
        }
    }
    return true;
}

void ICloudSyncOverlay::stateDirChanged()
{
    if (!load()) {
        return;
    }
    const QSet<QUrl> shown = m_shown;
    for (const QUrl &url : shown) {
        Q_EMIT overlaysChanged(url, overlaysFor(url.toLocalFile()));
    }
}

QStringList ICloudSyncOverlay::getOverlays(const QUrl &url)
{
    if (!url.isLocalFile()) {
        return {};
    }
    if (m_root.isEmpty()) {
        load(); // icloud-sync may have been set up after this file manager was started
    }
    const QString path = url.toLocalFile();
    if (m_root.isEmpty() || !path.startsWith(m_root)) {
        return {};
    }
    if (m_shown.size() > 20000) {
        m_shown.clear();
    }
    m_shown.insert(url);
    return overlaysFor(path);
}

QStringList ICloudSyncOverlay::overlaysFor(const QString &path) const
{
    const QString relative = path.mid(m_root.size());
    const QStringList components = relative.split(QLatin1Char('/'), Qt::SkipEmptyParts);
    for (const QString &component : components) {
        // Hidden and excluded names are never synced: no emblem rather than a misleading one.
        if (component.startsWith(QLatin1Char('.')) || QDir::match(m_exclude, component)) {
            return {};
        }
    }
    if (components.isEmpty()) {
        return {};
    }
    if (components.constLast().contains(QLatin1String(".conflict"))) {
        return {QStringLiteral("vcs-conflicting")};
    }
    const QFileInfo info(path);
    if (info.isDir()) {
        return {m_dirs.contains(relative) ? QStringLiteral("vcs-normal") : QStringLiteral("vcs-update-required")};
    }
    const auto known = m_files.constFind(relative);
    const bool synced = known != m_files.constEnd() && info.size() == known->size
        && info.lastModified(QTimeZone::UTC).toMSecsSinceEpoch() == known->mtimeMs;
    return {synced ? QStringLiteral("vcs-normal") : QStringLiteral("vcs-update-required")};
}

#include "icloudsyncoverlay.moc"
