// bobao-notify: copies new macOS notifications of chosen apps into ~/.bobao/notifications.jsonl,
// where Bobao reads them. It reads the system notification database, so this binary needs
// Full Disk Access (System Settings → Privacy & Security → Full Disk Access).
//
// Only apps listed in sources.notifications.apps of ~/.bobao/config.json are copied, plus
// the bare title of Feishu popups when the Feishu source is on (a nudge to read that group
// now). Nothing else leaves the database. The config is re-read on every check.
//
//   bobao-notify            run
//   bobao-notify --dump 20  print the last 20 notifications of any app (to find bundle ids)

import Foundation
import SQLite3

let home = FileManager.default.homeDirectoryForCurrentUser.path
let bobao = ProcessInfo.processInfo.environment["BOBAO_HOME"] ?? home + "/.bobao"
let dbPath = home + "/Library/Group Containers/group.com.apple.usernoted/db2/db"
let spoolPath = bobao + "/notifications.jsonl"
let configPath = bobao + "/config.json"

func log(_ s: String) {
    let f = DateFormatter()
    f.dateFormat = "yyyy-MM-dd HH:mm:ss"
    FileHandle.standardError.write("\(f.string(from: Date())) \(s)\n".data(using: .utf8)!)
}

struct Watch {
    var apps: [String] = []
    var lark = false

    static func load() -> Watch {
        var w = Watch()
        guard let data = FileManager.default.contents(atPath: configPath),
              let cfg = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sources = cfg["sources"] as? [String: Any] else { return w }
        if let n = sources["notifications"] as? [String: Any], n["enabled"] as? Bool ?? false {
            w.apps = (n["apps"] as? [String] ?? []).map { $0.lowercased() }
        }
        if let f = sources["feishu"] as? [String: Any] { w.lark = f["enabled"] as? Bool ?? false }
        return w
    }
}

struct Note {
    let key: String, app: String, title: String, subtitle: String, body: String, time: Double
}

func openDB() -> OpaquePointer? {
    var db: OpaquePointer?
    if sqlite3_open_v2(dbPath, &db, SQLITE_OPEN_READONLY, nil) != SQLITE_OK {
        log("打不开通知数据库：请在 系统设置 → 隐私与安全性 → 完全磁盘访问权限 里打开「Bobao 通知」")
        sqlite3_close(db)
        return nil
    }
    sqlite3_busy_timeout(db, 2000)
    return db
}

// The newest `limit` notifications, oldest first. rec_id is reused by the system, so the
// record uuid is what marks a notification as new.
func query(_ db: OpaquePointer, limit: Int) -> [Note] {
    let sql = "SELECT COALESCE(a.identifier, ''), r.data, r.uuid FROM record r LEFT JOIN app a ON a.app_id = r.app_id ORDER BY r.rec_id DESC LIMIT \(limit)"
    var stmt: OpaquePointer?
    guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
        log("查询失败: \(String(cString: sqlite3_errmsg(db)))")
        return []
    }
    defer { sqlite3_finalize(stmt) }
    var out: [Note] = []
    while sqlite3_step(stmt) == SQLITE_ROW {
        let app = String(cString: sqlite3_column_text(stmt, 0))
        var title = "", subtitle = "", body = ""
        var data = Data()
        if let blob = sqlite3_column_blob(stmt, 1) {
            data = Data(bytes: blob, count: Int(sqlite3_column_bytes(stmt, 1)))
            if let plist = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any],
               let req = plist["req"] as? [String: Any] {
                title = req["titl"] as? String ?? ""
                subtitle = req["subt"] as? String ?? ""
                body = req["body"] as? String ?? ""
            }
        }
        var key = ""
        if let u = sqlite3_column_blob(stmt, 2) {
            key = Data(bytes: u, count: Int(sqlite3_column_bytes(stmt, 2))).map { String(format: "%02x", $0) }.joined()
        }
        if key.isEmpty { key = "\(app)-\(data.hashValue)" }
        out.append(Note(key: key, app: app, title: title, subtitle: subtitle, body: body, time: Date().timeIntervalSince1970))
    }
    return out.reversed()
}

func append(_ obj: [String: Any]) {
    guard let line = try? JSONSerialization.data(withJSONObject: obj) else { return }
    let fm = FileManager.default
    if let size = (try? fm.attributesOfItem(atPath: spoolPath))?[.size] as? Int, size > 1_000_000 {
        try? fm.removeItem(atPath: spoolPath)   // Bobao notices the file shrank and starts over
    }
    if !fm.fileExists(atPath: spoolPath) { fm.createFile(atPath: spoolPath, contents: nil, attributes: [.posixPermissions: 0o600]) }
    guard let f = FileHandle(forWritingAtPath: spoolPath) else { return }
    f.seekToEndOfFile()
    f.write(line + "\n".data(using: .utf8)!)
    f.closeFile()
}

let args = CommandLine.arguments
if args.count >= 2 && args[1] == "--dump" {
    guard let db = openDB() else { exit(1) }
    for n in query(db, limit: args.count >= 3 ? Int(args[2]) ?? 20 : 20) {
        print("[\(n.app)] \(n.title) | \(n.subtitle) | \(n.body)")
    }
    exit(0)
}

enum Watcher {
    static var db: OpaquePointer!
    static let window = 300
    static var seen = Set<String>()

    static func check() {
        let w = Watch.load()
        let notes = query(db, limit: window)
        for n in notes where !seen.contains(n.key) {
            let app = n.app.lowercased()
            if w.apps.contains(where: { app.contains($0) }) {
                append(["app": n.app, "title": n.title, "subtitle": n.subtitle, "body": n.body, "time": n.time])
            } else if w.lark && (app.contains("com.electron.lark") || app.contains("feishu")) {
                append(["app": n.app, "title": n.title, "nudge": true, "time": n.time])
            }
        }
        seen = Set(notes.map { $0.key })
    }
}

guard let db = openDB() else { exit(1) }
Watcher.db = db
Watcher.seen = Set(query(db, limit: Watcher.window).map { $0.key })   // never copy the backlog
log("开始监听系统通知")
// The notification database sits in a protected folder where file events are unreliable,
// so it is re-read every 2 seconds (a local read only).
let timer = DispatchSource.makeTimerSource(queue: .main)
timer.schedule(deadline: .now() + 2, repeating: 2)
timer.setEventHandler { Watcher.check() }
timer.resume()
dispatchMain()
