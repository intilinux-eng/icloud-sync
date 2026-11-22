// SPDX-License-Identifier: MIT
// Loads the built plugin the way a file manager does and checks the emblems on a sandbox folder.

#include <KOverlayIconPlugin>

#include <QCoreApplication>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QPluginLoader>
#include <QTemporaryDir>
#include <QTextStream>
#include <QTimeZone>
#include <QUrl>

static int failures = 0;
static QTextStream out(stdout);

static void writeFile(const QString &path, const QByteArray &content)
{
    QDir().mkpath(QFileInfo(path).path());
    QFile file(path);
    if (file.open(QIODevice::WriteOnly)) {
        file.write(content);
    }
}

static QString record(const QString &root, const QString &relative)
{
    const QFileInfo info(root + QLatin1Char('/') + relative);
    return QStringLiteral("f\t%1\t%2\t%3\n").arg(info.size()).arg(info.lastModified(QTimeZone::UTC).toMSecsSinceEpoch()).arg(relative);
}

static void expect(KOverlayIconPlugin *plugin, const QString &path, const QStringList &wanted, const char *what)
{
    const QStringList got = plugin->getOverlays(QUrl::fromLocalFile(path));
    const bool ok = got == wanted;
    failures += ok ? 0 : 1;
    out << (ok ? "ok    " : "FAIL  ") << what << ": " << got.join(QLatin1Char(',')) << Qt::endl;
}

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QTemporaryDir tmp;
    const QString root = tmp.path() + QStringLiteral("/drive");
    const QString stateFile = tmp.path() + QStringLiteral("/state/icloud-sync/overlay-state.tsv");
    qputenv("XDG_STATE_HOME", (tmp.path() + QStringLiteral("/state")).toUtf8());

    writeFile(root + QStringLiteral("/synced.txt"), "same");
    writeFile(root + QStringLiteral("/changed.txt"), "edited after the last sync");
    writeFile(root + QStringLiteral("/new.txt"), "not uploaded yet");
    writeFile(root + QStringLiteral("/Docs/inside.txt"), "x");
    writeFile(root + QStringLiteral("/NewFolder/a.txt"), "x");
    writeFile(root + QStringLiteral("/report.conflict1.txt"), "x");
    writeFile(root + QStringLiteral("/Shared/doc.pdf"), "x");
    writeFile(root + QStringLiteral("/.hidden"), "x");
    writeFile(root + QStringLiteral("/draft.tmp"), "x");
    writeFile(tmp.path() + QStringLiteral("/elsewhere.txt"), "x");

    const QString header = QStringLiteral("icloud-sync-overlay\t1\nroot\t%1\nexclude\t*.tmp\nskip\tShared\nd\tDocs\n").arg(root);
    const QString firstState = header + record(root, QStringLiteral("synced.txt")) + QStringLiteral("f\t3\t1\tchanged.txt\n")
        + record(root, QStringLiteral("Docs/inside.txt"));
    writeFile(stateFile, firstState.toUtf8());

    QPluginLoader loader(QString::fromLocal8Bit(argv[1]));
    auto *plugin = qobject_cast<KOverlayIconPlugin *>(loader.instance());
    if (!plugin) {
        out << "FAIL  cannot load the plugin: " << loader.errorString() << Qt::endl;
        return 1;
    }

    const QStringList synced{QStringLiteral("vcs-normal")};
    const QStringList pending{QStringLiteral("vcs-update-required")};
    expect(plugin, root + QStringLiteral("/synced.txt"), synced, "file identical to the last sync");
    expect(plugin, root + QStringLiteral("/changed.txt"), pending, "file edited since the last sync");
    expect(plugin, root + QStringLiteral("/new.txt"), pending, "file never synced");
    expect(plugin, root + QStringLiteral("/Docs"), synced, "known folder");
    expect(plugin, root + QStringLiteral("/Docs/inside.txt"), synced, "file in a subfolder");
    expect(plugin, root + QStringLiteral("/NewFolder"), pending, "new folder");
    expect(plugin, root + QStringLiteral("/report.conflict1.txt"), {QStringLiteral("vcs-conflicting")}, "conflict copy");
    expect(plugin, root + QStringLiteral("/Shared"), {QStringLiteral("emblem-unavailable")}, "folder iCloud will not serve");
    expect(plugin, root + QStringLiteral("/Shared/doc.pdf"), {QStringLiteral("emblem-unavailable")}, "file inside it");
    expect(plugin, root + QStringLiteral("/.hidden"), {}, "hidden file");
    expect(plugin, root + QStringLiteral("/draft.tmp"), {}, "excluded file");
    expect(plugin, tmp.path() + QStringLiteral("/elsewhere.txt"), {}, "file outside the synced folder");

    // The daemon finishes a sync: the state file is replaced, and the item must be refreshed by a signal.
    QStringList announced;
    QObject::connect(plugin, &KOverlayIconPlugin::overlaysChanged, &app, [&](const QUrl &url, const QStringList &overlays) {
        if (url.fileName() == QLatin1String("new.txt")) {
            announced = overlays;
        }
    });
    QElapsedTimer timer;
    timer.start();
    while (timer.elapsed() < 1100) { // a later modification time, so the replacement is noticed
        QCoreApplication::processEvents(QEventLoop::AllEvents, 50);
    }
    writeFile(stateFile + QStringLiteral(".tmp"), (firstState + record(root, QStringLiteral("new.txt"))).toUtf8());
    QFile::remove(stateFile);
    QFile::rename(stateFile + QStringLiteral(".tmp"), stateFile);
    timer.restart();
    while (announced.isEmpty() && timer.elapsed() < 5000) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 50);
    }
    const bool refreshed = announced == synced;
    failures += refreshed ? 0 : 1;
    out << (refreshed ? "ok    " : "FAIL  ") << "item refreshed after the next sync: " << announced.join(QLatin1Char(',')) << Qt::endl;

    out << (failures ? "FAILED" : "ALL OK") << Qt::endl;
    return failures ? 1 : 0;
}
