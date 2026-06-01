"""Unit tests for Go and Rust language extractors."""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ccc.extractors.go import GoExtractor
from ccc.extractors.rust import RustExtractor

GO_SAMPLE = """\
package main

import (
    "fmt"
    "github.com/gin-gonic/gin"
    "github.com/user/myapp/internal"
)

type Server struct {
    port int
}

type Handler interface {
    Handle() error
}

func NewServer(port int) *Server {
    return &Server{port: port}
}

func (s *Server) Start() error {
    r := gin.Default()
    r.GET("/api/health", s.handleHealth)
    r.POST("/api/users", s.handleCreateUser)
    r.GET("/api/users/:id", s.handleGetUser)
    return r.Run()
}

func (s *Server) handleHealth(c *gin.Context) {
    c.JSON(200, gin.H{"status": "ok"})
}

func privateHelper() string {
    return "internal"
}
"""

RUST_SAMPLE = """\
use actix_web::{web, App, HttpServer};
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct User {
    pub id: u64,
    pub name: String,
}

pub enum UserError {
    NotFound,
}

pub trait UserService {
    fn get_user(&self, id: u64) -> Result<User, UserError>;
}

#[get("/api/users/{id}")]
pub async fn get_user(path: web::Path<u64>) -> impl Responder {
    HttpResponse::Ok().json("ok")
}

#[post("/api/users")]
pub async fn create_user(body: web::Json<User>) -> impl Responder {
    HttpResponse::Created().json("created")
}

pub fn configure_routes(cfg: &mut web::ServiceConfig) {
    cfg.service(get_user).service(create_user);
}

fn private_helper() -> String {
    String::from("internal")
}
"""

CARGO_TOML_SAMPLE = """\
[package]
name = "myapp"
version = "0.1.0"
edition = "2021"

[dependencies]
actix-web = "4"
serde = { version = "1", features = ["derive"] }
tokio = { version = "1", features = ["full"] }
"""

GO_MOD_SAMPLE = """\
module github.com/user/myapp

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/user/myapp/internal v0.1.0
)

require (
    golang.org/x/sys v0.13.0 // indirect
)
"""


class TestGoExtractor:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        (self.root / "main.go").write_text(GO_SAMPLE)
        (self.root / "go.mod").write_text(GO_MOD_SAMPLE)

    def test_extracts_exported_functions(self):
        result = GoExtractor(self.root).extract()
        names = [s.name for s in result.symbols]
        assert "NewServer" in names
        assert "Server.Start" in names

    def test_skips_unexported_functions(self):
        result = GoExtractor(self.root).extract()
        names = [s.name for s in result.symbols]
        assert "privateHelper" not in names

    def test_extracts_struct_types(self):
        result = GoExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "struct"]
        assert "Server" in names

    def test_extracts_interface_types(self):
        result = GoExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "interface"]
        assert "Handler" in names

    def test_extracts_gin_routes(self):
        result = GoExtractor(self.root).extract()
        paths = [r["path"] for r in result.routes]
        assert "/api/health" in paths
        assert "/api/users" in paths
        assert "/api/users/:id" in paths

    def test_extracts_route_methods(self):
        result = GoExtractor(self.root).extract()
        by_path = {r["path"]: r["method"] for r in result.routes}
        assert by_path.get("/api/health") == "GET"
        assert by_path.get("/api/users") == "POST"

    def test_parses_go_mod_module(self):
        result = GoExtractor(self.root).extract()
        assert any("go-module: github.com/user/myapp" in c for c in result.external_calls)

    def test_parses_go_mod_direct_deps(self):
        result = GoExtractor(self.root).extract()
        assert any("go-dep: github.com/gin-gonic/gin" in c for c in result.external_calls)

    def test_skips_indirect_deps(self):
        result = GoExtractor(self.root).extract()
        assert not any("golang.org/x/sys" in c for c in result.external_calls)

    def test_skips_test_files(self):
        (self.root / "main_test.go").write_text(
            'package main\nimport "testing"\nfunc TestFoo(t *testing.T) {}\n'
        )
        result = GoExtractor(self.root).extract()
        names = [s.name for s in result.symbols]
        assert "TestFoo" not in names

    def test_language_name(self):
        assert GoExtractor(self.root).language_name == "go"

    def test_file_patterns(self):
        assert "*.go" in GoExtractor(self.root).file_patterns


class TestRustExtractor:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        src = self.root / "src"
        src.mkdir()
        (src / "main.rs").write_text(RUST_SAMPLE)
        (self.root / "Cargo.toml").write_text(CARGO_TOML_SAMPLE)

    def test_extracts_pub_functions(self):
        result = RustExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "function"]
        assert "get_user" in names
        assert "create_user" in names
        assert "configure_routes" in names

    def test_skips_private_functions(self):
        result = RustExtractor(self.root).extract()
        names = [s.name for s in result.symbols]
        assert "private_helper" not in names

    def test_extracts_pub_structs(self):
        result = RustExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "struct"]
        assert "User" in names

    def test_extracts_pub_enums(self):
        result = RustExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "enum"]
        assert "UserError" in names

    def test_extracts_pub_traits(self):
        result = RustExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "trait"]
        assert "UserService" in names

    def test_extracts_actix_routes(self):
        result = RustExtractor(self.root).extract()
        paths = [r["path"] for r in result.routes]
        assert "/api/users/{id}" in paths
        assert "/api/users" in paths

    def test_extracts_route_methods(self):
        result = RustExtractor(self.root).extract()
        by_path = {r["path"]: r["method"] for r in result.routes}
        assert by_path.get("/api/users/{id}") == "GET"
        assert by_path.get("/api/users") == "POST"

    def test_route_framework_label(self):
        result = RustExtractor(self.root).extract()
        frameworks = {r["framework"] for r in result.routes}
        assert "actix-web" in frameworks

    def test_parses_cargo_toml_crate_name(self):
        result = RustExtractor(self.root).extract()
        assert any("rust-crate: myapp" in c for c in result.external_calls)

    def test_parses_cargo_toml_dependencies(self):
        result = RustExtractor(self.root).extract()
        dep_names = [c for c in result.external_calls if c.startswith("rust-dep:")]
        dep_crates = [d.replace("rust-dep: ", "") for d in dep_names]
        assert "actix-web" in dep_crates
        assert "serde" in dep_crates
        assert "tokio" in dep_crates

    def test_types_populated(self):
        result = RustExtractor(self.root).extract()
        type_names = [t["name"] for t in result.types]
        assert "User" in type_names

    def test_language_name(self):
        assert RustExtractor(self.root).language_name == "rust"

    def test_file_patterns(self):
        assert "*.rs" in RustExtractor(self.root).file_patterns
