use zed_extension_api::{self as zed, ContextServerId, Result};

struct Latex2ArxivExtension;

impl zed::Extension for Latex2ArxivExtension {
    fn new() -> Self {
        Self
    }

    fn context_server_command(
        &mut self,
        _context_server_id: &ContextServerId,
        _project: &zed::Project,
    ) -> Result<zed::Command> {
        Ok(zed::Command {
            command: "latex2arxiv-mcp".into(),
            args: vec![],
            env: vec![],
        })
    }
}

zed::register_extension!(Latex2ArxivExtension);
