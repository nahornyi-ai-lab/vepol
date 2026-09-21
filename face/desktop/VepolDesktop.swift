import AppKit
import Foundation
import Security
import UserNotifications
import WebKit

private struct LaunchConfiguration {
    var port = 8781
    var hub: String?
    var stateDirectory: String?

    init(arguments: [String]) throws {
        guard let index = arguments.firstIndex(of: "--test-config") else { return }
        guard arguments.indices.contains(index + 1) else {
            throw ShellError.message("После --test-config требуется путь к файлу.")
        }
        let data = try Data(contentsOf: URL(fileURLWithPath: arguments[index + 1]))
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ShellError.message("Не удалось прочитать конфигурацию проверки.")
        }
        if let value = object["port"] as? Int { port = value }
        hub = object["hub"] as? String
        stateDirectory = object["state_dir"] as? String
        guard (1...65535).contains(port), stateDirectory != nil else {
            throw ShellError.message("Проверке нужны отдельное state_dir и допустимый порт.")
        }
    }

    var origin: String { "http://127.0.0.1:\(port)" }
}

private enum ShellError: Error, LocalizedError {
    case message(String)
    var errorDescription: String? {
        if case let .message(message) = self { return message }
        return nil
    }
}

@MainActor
final class VepolApplication: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, UNUserNotificationCenterDelegate {
    private var configuration: LaunchConfiguration?
    private var window: NSWindow!
    private var webView: WKWebView?
    private var backend: Process?
    private var inputPipe: Pipe?
    private var outputPipe: Pipe?
    private var errorPipe: Pipe?
    private var outputBuffer = Data()
    private var lastError = ""
    private var token = ""
    private var backendReady = false
    private var bootstrapFailed = false
    private var terminationPending = false
    private var shuttingDown = false
    private var statusRequestActive = false
    private var statusTimer: Timer?
    private var pendingRequests = 0
    private var launchID = UUID()
    private var notificationAuthorizationRequested = false
    private let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        configuration.httpCookieStorage = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 8
        return URLSession(configuration: configuration)
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Vepol"
        window.minSize = NSSize(width: 760, height: 540)
        window.isReleasedWhenClosed = false
        window.center()
        showWindow()
        UNUserNotificationCenter.current().delegate = self
        do {
            configuration = try LaunchConfiguration(arguments: CommandLine.arguments)
            startBackend()
        } catch {
            showFailure(error.localizedDescription)
        }
    }

    private func buildMenu() {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "О Vepol", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Скрыть Vepol", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Завершить Vepol", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menu.addItem(appItem)
        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Правка")
        for (title, selector, key) in [("Отменить", "undo:", "z"), ("Вырезать", "cut:", "x"), ("Копировать", "copy:", "c"), ("Вставить", "paste:", "v"), ("Выделить всё", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: NSSelectorFromString(selector), keyEquivalent: key)
        }
        editItem.submenu = edit
        menu.addItem(editItem)
        let windowItem = NSMenuItem()
        let windowMenu = NSMenu(title: "Окно")
        let reopen = windowMenu.addItem(withTitle: "Открыть Vepol", action: #selector(showWindow), keyEquivalent: "0")
        reopen.target = self
        let reload = windowMenu.addItem(withTitle: "Обновить", action: #selector(reloadPage), keyEquivalent: "r")
        reload.target = self
        windowMenu.addItem(withTitle: "Закрыть окно", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        windowItem.submenu = windowMenu
        menu.addItem(windowItem)
        NSApp.mainMenu = menu
        NSApp.windowsMenu = windowMenu
    }

    @objc private func showWindow() {
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func reloadPage() { webView?.reload() }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    private func statusView(_ text: String, retry: Bool = false) {
        let label = NSTextField(wrappingLabelWithString: text)
        label.alignment = .center
        label.font = .systemFont(ofSize: 16)
        let stack = NSStackView(views: [label])
        stack.orientation = .vertical
        stack.spacing = 20
        if retry {
            stack.addArrangedSubview(NSButton(title: "Повторить", target: self, action: #selector(retryBackend)))
        }
        let container = NSView()
        container.addSubview(stack)
        stack.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: container.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: container.centerYAnchor),
            stack.widthAnchor.constraint(lessThanOrEqualToConstant: 680),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: container.leadingAnchor, constant: 32),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: container.trailingAnchor, constant: -32),
        ])
        window.contentView = container
    }

    private func showFailure(_ message: String) {
        let safeMessage = token.isEmpty ? message : message.replacingOccurrences(of: token, with: "[скрыто]")
        statusView("Vepol не удалось запустить.\n\n\(safeMessage)", retry: configuration != nil)
    }

    @objc private func retryBackend() {
        guard backend?.isRunning != true else { return }
        startBackend()
    }

    private func backendDirectory() throws -> URL {
        guard let resource = Bundle.main.url(forResource: "backend-path", withExtension: "txt") else {
            throw ShellError.message("В сборке отсутствует путь к backend. Пересоберите приложение через desktop/build.sh.")
        }
        let path = try String(contentsOf: resource, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        let directory = URL(fileURLWithPath: path, isDirectory: true)
        guard FileManager.default.isExecutableFile(atPath: directory.appendingPathComponent(".venv/bin/python").path) else {
            throw ShellError.message("Не найден Python окружения Vepol. Восстановите .venv в каталоге backend и нажмите «Повторить».")
        }
        return directory
    }

    private func childEnvironment() -> [String: String] {
        let removed: Set<String> = ["OPENAI_API_KEY", "AI_AGENT", "ANTHROPIC_BASE_URL", "CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_RUN_ID", "CODEX_JOB_ID", "CODEX_TURN_ID", "AGENT_SESSION_ID", "AGENT_ID", "VEPOL_FACE_STATE_DIR"]
        var environment = ProcessInfo.processInfo.environment.filter {
            !removed.contains($0.key) && !$0.key.hasPrefix("CLAUDE") && !$0.key.hasPrefix("CODEX_COMPANION_")
        }
        environment["PATH"] = [FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin").path,
                               "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"].joined(separator: ":")
        environment["PYTHONUNBUFFERED"] = "1"
        return environment
    }

    private func startBackend() {
        guard let configuration, backend?.isRunning != true else { return }
        statusTimer?.invalidate()
        statusTimer = nil
        backendReady = false
        bootstrapFailed = false
        launchID = UUID()
        let generation = launchID
        outputBuffer = Data()
        lastError = ""
        webView = nil
        statusView("Запускаю Vepol…")
        do {
            let directory = try backendDirectory()
            var randomBytes = [UInt8](repeating: 0, count: 32)
            guard SecRandomCopyBytes(kSecRandomDefault, randomBytes.count, &randomBytes) == errSecSuccess else {
                throw ShellError.message("Не удалось создать защищённый ключ запуска.")
            }
            token = Data(randomBytes).base64EncodedString().replacingOccurrences(of: "+", with: "-")
                .replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
            let child = Process()
            child.executableURL = directory.appendingPathComponent(".venv/bin/python")
            child.arguments = ["-m", "vepol_face.desktop_server"]
            child.currentDirectoryURL = directory
            child.environment = childEnvironment()
            let input = Pipe(), output = Pipe(), errors = Pipe()
            inputPipe = input
            outputPipe = output
            errorPipe = errors
            child.standardInput = input
            child.standardOutput = output
            child.standardError = errors
            output.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                if data.isEmpty { handle.readabilityHandler = nil; return }
                Task { @MainActor in
                    guard self?.launchID == generation else { return }
                    self?.receiveOutput(data)
                }
            }
            errors.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                if data.isEmpty { handle.readabilityHandler = nil; return }
                let text = String(decoding: data, as: UTF8.self)
                Task { @MainActor in
                    guard let self, self.launchID == generation else { return }
                    self.lastError = String((self.lastError + text).suffix(2000))
                }
            }
            child.terminationHandler = { [weak self] process in
                Task { @MainActor in
                    guard self?.launchID == generation else { return }
                    self?.backendExited(status: process.terminationStatus)
                }
            }
            backend = child
            try child.run()
            var bootstrap: [String: Any] = ["token": token, "port": configuration.port]
            if let hub = configuration.hub { bootstrap["hub"] = hub }
            if let stateDirectory = configuration.stateDirectory { bootstrap["state_dir"] = stateDirectory }
            var line = try JSONSerialization.data(withJSONObject: bootstrap)
            line.append(10)
            try input.fileHandleForWriting.write(contentsOf: line)
        } catch {
            try? inputPipe?.fileHandleForWriting.close()
            bootstrapFailed = true
            showFailure(error.localizedDescription)
        }
    }

    private func receiveOutput(_ data: Data) {
        guard !backendReady && !bootstrapFailed else { return }
        outputBuffer.append(data)
        while let newline = outputBuffer.firstIndex(of: 10) {
            let line = outputBuffer.subdata(in: 0..<newline)
            outputBuffer.removeSubrange(0...newline)
            guard let object = (try? JSONSerialization.jsonObject(with: line)) as? [String: Any] else { continue }
            if object["ready"] as? Bool == true, object["port"] as? Int == configuration?.port {
                backendReady = true
                waitForListener(generation: launchID)
                return
            }
            if let message = object["error"] as? String {
                bootstrapFailed = true
                let holder = object["holder"] as? String
                let pid = (object["pid"] as? Int).map { " (PID \($0))" } ?? ""
                let detail = holder.map { "\nПорт занимает \($0)\(pid)." } ?? ""
                showFailure(message + detail)
                return
            }
        }
    }

    private func waitForListener(generation: UUID) {
        Task {
            guard launchID == generation, backendReady, backend?.isRunning == true else { return }
            do {
                _ = try await request("/api/desktop/status")
                guard launchID == generation, backendReady else { return }
                loadInterface()
            } catch {
                guard launchID == generation, backendReady else { return }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
                    self?.waitForListener(generation: generation)
                }
            }
        }
    }

    private func loadInterface() {
        guard let configuration else { return }
        let webConfiguration = WKWebViewConfiguration()
        webConfiguration.websiteDataStore = .nonPersistent()
        let quotedToken = String(data: try! JSONSerialization.data(withJSONObject: token, options: [.fragmentsAllowed]), encoding: .utf8)!
        let quotedOrigin = String(data: try! JSONSerialization.data(withJSONObject: configuration.origin, options: [.fragmentsAllowed]), encoding: .utf8)!
        let injection = "if (window.location.origin === \(quotedOrigin)) { Object.defineProperty(window, '__VEPOL_TOKEN__', {value: \(quotedToken)}); }"
        webConfiguration.userContentController.addUserScript(WKUserScript(source: injection, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let view = WKWebView(frame: window.contentView?.bounds ?? .zero, configuration: webConfiguration)
        view.autoresizingMask = [.width, .height]
        view.navigationDelegate = self
        view.uiDelegate = self
        webView = view
        window.contentView = view
        view.load(URLRequest(url: URL(string: configuration.origin + "/")!))
        statusTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.pollStatus() }
        }
        pollStatus()
    }

    private func isBackendURL(_ url: URL) -> Bool {
        guard let configuration else { return false }
        return url.scheme == "http" && url.host == "127.0.0.1" && url.port == configuration.port && url.user == nil && url.password == nil
    }

    private func openExternal(_ url: URL) {
        guard ["https", "http", "mailto"].contains(url.scheme?.lowercased() ?? "") else { return }
        guard !url.absoluteString.contains(token) else { return }
        NSWorkspace.shared.open(url)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if isBackendURL(url) {
            decisionHandler(.allow)
        } else {
            decisionHandler(.cancel)
            if navigationAction.targetFrame?.isMainFrame != false { openExternal(url) }
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            if isBackendURL(url) { webView.load(navigationAction.request) }
            else { openExternal(url) }
        }
        return nil
    }

    private func request(_ path: String, method: String = "GET") async throws -> [String: Any] {
        guard let configuration else { throw ShellError.message("Vepol ещё не настроен.") }
        var request = URLRequest(url: URL(string: configuration.origin + path)!)
        request.httpMethod = method
        request.setValue(token, forHTTPHeaderField: "X-Vepol-Token")
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse, (200...299).contains(response.statusCode) else {
            throw ShellError.message("Backend пока не подтвердил состояние сессий.")
        }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
    }

    private func pollStatus() {
        guard backendReady, backend?.isRunning == true, !statusRequestActive, !shuttingDown else { return }
        statusRequestActive = true
        Task {
            defer { statusRequestActive = false }
            guard let status = try? await request("/api/desktop/status") else { return }
            let count = status["pending"] as? Int ?? 0
            NSApp.dockTile.badgeLabel = count > 0 ? String(count) : nil
            if count > pendingRequests { notifyOwner(count: count) }
            pendingRequests = count
        }
    }

    private func notifyOwner(count: Int) {
        let center = UNUserNotificationCenter.current()
        Task {
            if !notificationAuthorizationRequested {
                notificationAuthorizationRequested = true
                _ = try? await center.requestAuthorization(options: [.alert, .badge, .sound])
            }
            let content = UNMutableNotificationContent()
            content.title = "Vepol ждёт вашего ответа"
            content.body = count == 1 ? "Одна сессия требует вашего решения." : "Сессий, ожидающих решения: \(count)."
            content.sound = .default
            try? await center.add(UNNotificationRequest(identifier: "vepol-owner-attention", content: content, trigger: nil))
        }
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        Task { @MainActor in self.showWindow() }
        completionHandler()
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if backend?.isRunning != true { return .terminateNow }
        guard !terminationPending else { return .terminateCancel }
        terminationPending = true
        Task { await checkQuit() }
        return .terminateLater
    }

    private func cancelQuit(message: String) {
        terminationPending = false
        shuttingDown = false
        NSApp.reply(toApplicationShouldTerminate: false)
        let alert = NSAlert()
        alert.messageText = "Vepol продолжает работу"
        alert.informativeText = message
        alert.addButton(withTitle: "Продолжить работу")
        alert.addButton(withTitle: "Открыть Vepol")
        if alert.runModal() == .alertSecondButtonReturn { showWindow() }
    }

    private func checkQuit() async {
        do {
            let status = try await request("/api/desktop/status")
            guard status["busy"] as? Bool == false else {
                cancelQuit(message: "Есть активные сессии или запросы на решение. Они останутся запущенными. Дождитесь завершения работы или остановите нужную сессию в приложении.")
                return
            }
            shuttingDown = true
            _ = try await request("/api/desktop/shutdown", method: "POST")
            // The owned backend closes its idle clients and exits naturally.
            // Its termination handler is the only successful quit confirmation.
        } catch {
            if backend?.isRunning != true {
                NSApp.reply(toApplicationShouldTerminate: true)
            } else {
                cancelQuit(message: "Не удалось подтвердить безопасное завершение backend. Сессии сохранены. Повторите завершение, когда связь восстановится.")
            }
        }
    }

    private func backendExited(status: Int32) {
        backendReady = false
        statusTimer?.invalidate()
        statusTimer = nil
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        errorPipe?.fileHandleForReading.readabilityHandler = nil
        try? inputPipe?.fileHandleForWriting.close()
        NSApp.dockTile.badgeLabel = nil
        if terminationPending && shuttingDown {
            NSApp.reply(toApplicationShouldTerminate: true)
        } else if !bootstrapFailed {
            showFailure("Backend завершился (код \(status)).\n\(lastError)")
        }
    }
}

@main
enum VepolDesktop {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = VepolApplication()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.run()
    }
}
