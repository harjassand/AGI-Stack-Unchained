use crate::kernel_sys;

pub enum Command {
    BrainSuite { suitepack: String, out_dir: String },
}

pub struct CliArgs {
    pub command: Command,
}

pub fn parse_args() -> Result<CliArgs, String> {
    let args = kernel_sys::args();
    if args.len() != 6 {
        return Err("INVALID:KERNEL_EXIT_CODE:30".to_string());
    }
    if args[1] != "brain-suite" || args[2] != "--suitepack" || args[4] != "--out_dir" {
        return Err("INVALID:KERNEL_EXIT_CODE:30".to_string());
    }
    Ok(CliArgs {
        command: Command::BrainSuite {
            suitepack: args[3].clone(),
            out_dir: args[5].clone(),
        },
    })
}
