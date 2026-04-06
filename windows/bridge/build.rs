fn main() {
    // Embed icon into the launcher exe (icon is copied by CI before cargo build)
    if std::path::Path::new("launcher.rc").exists()
        && std::path::Path::new("mixtapes.ico").exists()
    {
        let _ = embed_resource::compile("launcher.rc", embed_resource::NONE);
    }
}
