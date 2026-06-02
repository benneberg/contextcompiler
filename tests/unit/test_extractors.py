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


# ── C# extractor tests ────────────────────────────────────────────────────────

CSHARP_SAMPLE = """\
using Microsoft.AspNetCore.Mvc;
using MyApp.Services;
using Stripe;

namespace MyApp.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class UsersController : ControllerBase
    {
        private readonly IUserService _service;

        public UsersController(IUserService service)
        {
            _service = service;
        }

        [HttpGet]
        public async Task<IActionResult> GetAll()
        {
            return Ok(await _service.GetAllAsync());
        }

        [HttpGet("{id}")]
        public async Task<IActionResult> GetById(int id)
        {
            return Ok(await _service.GetByIdAsync(id));
        }

        [HttpPost]
        public async Task<IActionResult> Create([FromBody] CreateUserRequest request)
        {
            return CreatedAtAction(nameof(GetById), await _service.CreateAsync(request));
        }

        [HttpDelete("{id}")]
        public async Task<IActionResult> Delete(int id)
        {
            await _service.DeleteAsync(id);
            return NoContent();
        }

        private string InternalHelper() => "private";
    }

    public interface IUserService
    {
        Task<IEnumerable<User>> GetAllAsync();
    }

    public record User(int Id, string Name, string Email);

    public enum UserStatus { Active, Inactive, Banned }
}
"""

MINIMAL_API_SAMPLE = """\
using Microsoft.AspNetCore.Builder;

var app = WebApplication.Create(args);

app.MapGet("/api/health", () => "ok");
app.MapPost("/api/items", (Item item) => Results.Created());
app.MapPut("/api/items/{id}", (int id, Item item) => Results.Ok());
app.MapDelete("/api/items/{id}", (int id) => Results.Ok());

app.Run();
"""

CSPROJ_SAMPLE = """\
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <AssemblyName>MyApp.Api</AssemblyName>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Stripe.net" Version="43.0.0" />
    <PackageReference Include="Serilog.AspNetCore" Version="8.0.0" />
    <PackageReference Include="AutoMapper" Version="12.0.0" />
  </ItemGroup>
</Project>
"""


class TestCSharpExtractor:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        src = self.root / "Controllers"
        src.mkdir()
        (src / "UsersController.cs").write_text(CSHARP_SAMPLE)
        (self.root / "Program.cs").write_text(MINIMAL_API_SAMPLE)
        (self.root / "MyApp.csproj").write_text(CSPROJ_SAMPLE)

    def test_extracts_public_methods(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "method"]
        assert any("GetAll" in n for n in names)
        assert any("GetById" in n for n in names)
        assert any("Create" in n for n in names)
        assert any("Delete" in n for n in names)

    def test_skips_private_methods(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        names = [s.name for s in result.symbols]
        assert not any("InternalHelper" in n for n in names)

    def test_extracts_classes(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "class"]
        assert "UsersController" in names

    def test_extracts_interfaces(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "interface"]
        assert "IUserService" in names

    def test_extracts_records(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "record"]
        assert "User" in names

    def test_extracts_enums(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        names = [s.name for s in result.symbols if s.kind == "enum"]
        assert "UserStatus" in names

    def test_extracts_attribute_routes(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        methods = {r["method"] for r in result.routes}
        assert "GET" in methods
        assert "POST" in methods
        assert "DELETE" in methods

    def test_extracts_minimal_api_routes(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        paths = [r["path"] for r in result.routes]
        assert "/api/health" in paths
        assert "/api/items" in paths

    def test_minimal_api_framework_label(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        frameworks = {r["framework"] for r in result.routes}
        assert "minimal-api" in frameworks

    def test_parses_csproj_assembly_name(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        assert any("csharp-assembly: MyApp.Api" in c for c in result.external_calls)

    def test_parses_csproj_dependencies(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        deps = [c for c in result.external_calls if c.startswith("csharp-dep:")]
        dep_names = [d.replace("csharp-dep: ", "") for d in deps]
        assert "Stripe.net" in dep_names
        assert "Serilog.AspNetCore" in dep_names
        assert "AutoMapper" in dep_names

    def test_extracts_external_usings(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        all_imports = []
        for imps in result.imports.values():
            all_imports.extend(imps)
        assert any("MyApp.Services" in i for i in all_imports)
        assert any("Stripe" in i for i in all_imports)

    def test_skips_microsoft_usings(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        all_imports = []
        for imps in result.imports.values():
            all_imports.extend(imps)
        # Microsoft and System namespaces should be filtered
        assert not any(i.startswith("System") for i in all_imports)

    def test_types_populated(self):
        from ccc.extractors.csharp import CSharpExtractor
        result = CSharpExtractor(self.root).extract()
        type_names = [t["name"] for t in result.types]
        assert "UsersController" in type_names
        assert "IUserService" in type_names

    def test_language_name(self):
        from ccc.extractors.csharp import CSharpExtractor
        assert CSharpExtractor(self.root).language_name == "csharp"

    def test_file_patterns(self):
        from ccc.extractors.csharp import CSharpExtractor
        assert "*.cs" in CSharpExtractor(self.root).file_patterns

    def test_skips_generated_files(self):
        from ccc.extractors.csharp import CSharpExtractor
        gen_dir = self.root / "Generated"
        gen_dir.mkdir()
        (gen_dir / "Model.g.cs").write_text("public class Generated { public void Foo() {} }")
        result = CSharpExtractor(self.root).extract()
        names = [s.name for s in result.symbols]
        assert "Generated" not in names
