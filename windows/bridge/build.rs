fn main() {
    if std::path::Path::new("mixtapes.ico").exists()
        && std::path::Path::new("launcher.rc").exists()
    {
        let _ = embed_resource::compile("launcher.rc", embed_resource::NONE);
    }
}
