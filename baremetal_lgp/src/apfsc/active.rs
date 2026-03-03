use std::path::Path;

use crate::apfsc::artifacts::{read_pointer, write_pointer};
use crate::apfsc::errors::Result;

pub fn read_active_search_law(root: &Path) -> Result<String> {
    read_pointer(root, "active_search_law")
}

pub fn write_active_search_law(root: &Path, searchlaw_hash: &str) -> Result<()> {
    write_pointer(root, "active_search_law", searchlaw_hash)
}

pub fn read_active_incubator_pointer(root: &Path) -> Result<String> {
    read_pointer(root, "active_incubator_pointer")
}

pub fn write_active_incubator_pointer(root: &Path, candidate_hash: &str) -> Result<()> {
    write_pointer(root, "active_incubator_pointer", candidate_hash)
}

pub fn read_active_incubator_search_law(root: &Path) -> Result<String> {
    read_pointer(root, "active_incubator_search_law")
}

pub fn write_active_incubator_search_law(root: &Path, searchlaw_hash: &str) -> Result<()> {
    write_pointer(root, "active_incubator_search_law", searchlaw_hash)
}

pub fn read_active_epoch_mode(root: &Path) -> Result<String> {
    read_pointer(root, "active_epoch_mode")
}

pub fn write_active_epoch_mode(root: &Path, mode: &str) -> Result<()> {
    write_pointer(root, "active_epoch_mode", mode)
}

pub fn write_active_incubator_error_atlas(root: &Path, path: &str) -> Result<()> {
    write_pointer(root, "active_incubator_error_atlas", path)
}

pub fn read_active_class_h_hypothesis(root: &Path) -> Result<String> {
    read_pointer(root, "active_class_h_hypothesis")
}

pub fn write_active_class_h_hypothesis(root: &Path, hypothesis_id: &str) -> Result<()> {
    write_pointer(root, "active_class_h_hypothesis", hypothesis_id)
}

pub fn read_active_class_m_material(root: &Path) -> Result<String> {
    read_pointer(root, "active_class_m_material")
}

pub fn write_active_class_m_material(root: &Path, material_id: &str) -> Result<()> {
    write_pointer(root, "active_class_m_material", material_id)
}

pub fn read_active_discovery_constraints_hash(root: &Path) -> Result<String> {
    read_pointer(root, "active_discovery_constraints_hash")
}

pub fn write_active_discovery_constraints_hash(root: &Path, hash: &str) -> Result<()> {
    write_pointer(root, "active_discovery_constraints_hash", hash)
}

pub fn read_active_formal_policy(root: &Path) -> Result<String> {
    read_pointer(root, "active_formal_policy")
}

pub fn write_active_formal_policy(root: &Path, policy_hash: &str) -> Result<()> {
    write_pointer(root, "active_formal_policy", policy_hash)
}
