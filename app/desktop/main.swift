// F5 Studio: a native window around the local F5 Studio web UI (same idea as Circle).
// Launch starts the local server (app/run_server.sh) unless it's already up; Quit stops it.
import Cocoa
import WebKit

let home = FileManager.default.homeDirectoryForCurrentUser.path
let port = 8799
let startURL = URL(string: "http://127.0.0.1:\(port)/app/ui/index.html?app=1")!
let serverScript = "\(home)/f5-tts/app/run_server.sh"
let logPath = "\(home)/f5-tts/app/server.log"

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    var loading: NSTextField!

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenu()
        buildWindow()
        if serverIsUp() { load() } else { startServer(); waitForServer(tries: 120) }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ note: Notification) {
        guard let s = server, s.isRunning else { return }
        s.terminate()   // SIGTERM to the server; it finishes the clip it's on and exits
        s.waitUntilExit()
    }

    // MARK: window

    func buildWindow() {
        let config = WKWebViewConfiguration()
        config.mediaTypesRequiringUserActionForPlayback = []
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.setValue(false, forKey: "drawsBackground")   // no white flash before the page paints

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "F5 Studio"
        window.titlebarAppearsTransparent = true   // title bar blends with the window, still draggable
        window.minSize = NSSize(width: 820, height: 560)
        window.delegate = self
        window.setFrameAutosaveName("F5StudioMain")
        if window.frame.origin == .zero { window.center() }

        let root = NSView()
        root.wantsLayer = true
        root.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
        web.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(web)

        loading = NSTextField(labelWithString: "Starting F5 Studio…")
        loading.font = .systemFont(ofSize: 15, weight: .medium)
        loading.textColor = .secondaryLabelColor
        loading.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(loading)

        NSLayoutConstraint.activate([
            web.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            web.topAnchor.constraint(equalTo: root.topAnchor),
            web.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            loading.centerXAnchor.constraint(equalTo: root.centerXAnchor),
            loading.centerYAnchor.constraint(equalTo: root.centerYAnchor),
        ])
        window.contentView = root
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func load() {
        web.load(URLRequest(url: startURL))
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loading.isHidden = true
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        loading.isHidden = false
        loading.stringValue = "Couldn't reach F5 Studio. See ~/f5-tts/app/server.log"
    }

    // Links to anything other than the local app open in the default browser.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, url.host != "127.0.0.1", url.host != "localhost", url.scheme?.hasPrefix("http") == true {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    // <input type="file"> → the normal macOS open panel.
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = message
        a.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = message
        a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    // MARK: server

    func serverIsUp() -> Bool {
        var req = URLRequest(url: startURL); req.timeoutInterval = 0.5
        let sem = DispatchSemaphore(value: 0); var ok = false
        URLSession.shared.dataTask(with: req) { _, resp, _ in
            ok = (resp as? HTTPURLResponse)?.statusCode == 200; sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 1)
        return ok
    }

    func startServer() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = [serverScript, String(port)]
        p.currentDirectoryURL = URL(fileURLWithPath: "\(home)/f5-tts")
        FileManager.default.createFile(atPath: logPath, contents: nil)
        if let log = FileHandle(forWritingAtPath: logPath) { p.standardOutput = log; p.standardError = log }
        do { try p.run(); server = p } catch {
            loading.stringValue = "Couldn't start F5 Studio: \(error.localizedDescription)"
        }
    }

    func waitForServer(tries: Int) {
        DispatchQueue.global().async {
            let up = self.serverIsUp()
            DispatchQueue.main.async {
                if up { self.load(); return }
                if tries <= 0 || self.server?.isRunning == false {
                    self.loading.stringValue = "F5 Studio didn't start. See ~/f5-tts/app/server.log"
                    return
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.waitForServer(tries: tries - 1) }
            }
        }
    }

    // MARK: menus

    @objc func reload() { web.reload() }
    @objc func openFolder() { NSWorkspace.shared.open(URL(fileURLWithPath: "\(home)/f5-tts")) }

    func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About F5 Studio", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide F5 Studio", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit F5 Studio", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu

        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit

        let viewItem = NSMenuItem(); main.addItem(viewItem)
        let view = NSMenu(title: "View")
        view.addItem(withTitle: "Reload", action: #selector(reload), keyEquivalent: "r")
        view.addItem(withTitle: "Show Project Folder", action: #selector(openFolder), keyEquivalent: "")
        viewItem.submenu = view

        let winItem = NSMenuItem(); main.addItem(winItem)
        let win = NSMenu(title: "Window")
        win.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        winItem.submenu = win
        NSApp.windowsMenu = win

        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
