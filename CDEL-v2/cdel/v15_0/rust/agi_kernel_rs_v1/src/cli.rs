use crate::kernel_sys;

pub enum Command {
    Run { run_spec: String },
}

pub struct CliArgs {
    pub command: Command,
}

pub fn parse_args() -> Result<CliArgs, String> {
    let args = kernel_sys::args();
    if args.len() != 4 {
        return Err("INVALID:KERNEL_EXIT_CODE:30".to_string());
    }
    if args[1] != "run" || args[2] != "--run_spec" {
        return Err("INVALID:KERNEL_EXIT_CODE:30".to_string());
    }
    Ok(CliArgs {
        command: Command::Run {
            run_spec: args[3].clone(),
        },
    })
}
