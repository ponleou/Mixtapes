fn main() {
    let target = std::env::var("CARGO_BIN_NAME").unwrap_or_default();

    if target == "MixtapesBridge" {
        // Bridge gets manifest (for sparse package identity) + version info
        if std::path::Path::new("bridge.rc").exists() {
            let _ = embed_resource::compile("bridge.rc", embed_resource::NONE);
        }
    } else if target == "Mixtapes" {
        // Launcher gets icon + version info
        if std::path::Path::new("mixtapes.ico").exists()
            && std::path::Path::new("launcher.rc").exists()
        {
            let _ = embed_resource::compile("launcher.rc", embed_resource::NONE);
        }
    }
}
