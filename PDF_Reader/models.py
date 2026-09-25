"""Entidades de domínio do MangaReader 2000.

Dataclasses puras — sem dependência de UI, arquivo ou rede.
Isso permite serializar para JSON local hoje e para payload de API amanhã.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, asdict, field
from typing import List, Optional


@dataclass
class Review:
    id: str
    perfil: str
    obra: str
    nota: int
    texto: str
    data: str
    editada_em: Optional[str] = None

    @classmethod
    def nova(cls, perfil: str, obra: str, nota: int, texto: str) -> "Review":
        return cls(
            id=uuid.uuid4().hex,
            perfil=perfil,
            obra=obra,
            nota=nota,
            texto=texto,
            data=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Review":
        try:
            nota = int(d.get("nota", 5))
        except (TypeError, ValueError):
            nota = 5
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex),
            perfil=str(d.get("perfil", "Leitor")),
            obra=str(d.get("obra", "")),
            nota=max(1, min(5, nota)),
            texto=str(d.get("texto", "")),
            data=str(d.get("data", "")),
            editada_em=d.get("editada_em"),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Mensagem:
    autor: str
    texto: str
    hora: str

    @classmethod
    def nova(cls, autor: str, texto: str) -> "Mensagem":
        return cls(autor=autor, texto=texto,
                   hora=datetime.datetime.now().strftime("%H:%M"))

    @classmethod
    def from_dict(cls, d: dict) -> "Mensagem":
        return cls(
            autor=str(d.get("autor", "")),
            texto=str(d.get("texto", "")),
            hora=str(d.get("hora", "")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProgressoLeitura:
    ultima_pagina: int = 0
    concluido: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "ProgressoLeitura":
        try:
            pagina = int(d.get("ultima_pagina", 0))
        except (TypeError, ValueError):
            pagina = 0
        if pagina < 0:
            pagina = 0

        # bool("false") == True, então validamos o tipo antes de converter.
        # Aceita: true/false (JSON padrão), 1/0, "true"/"false", "sim"/"não".
        bruto = d.get("concluido", False)
        if isinstance(bruto, bool):
            concluido = bruto
        else:
            concluido = str(bruto).strip().lower() in ("true", "1", "sim", "yes")

        return cls(ultima_pagina=pagina, concluido=concluido)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Perfil:
    """Um perfil de usuário.

    O `nome` é o identificador *visível* e é o que as reviews usam para
    referenciar o autor (campo Review.perfil). O `id` é estável e usado
    internamente (nome de arquivo de foto, referências futuras etc).
    """
    id: str
    nome: str
    bio: str = ""
    foto_path: str = ""
    favoritos: List[str] = field(default_factory=list)
    criado_em: str = ""

    @classmethod
    def novo(cls, nome: str, bio: str = "") -> "Perfil":
        return cls(
            id=uuid.uuid4().hex,
            nome=nome,
            bio=bio,
            foto_path="",
            favoritos=[],
            criado_em=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Perfil":
        favoritos = d.get("favoritos")
        if not isinstance(favoritos, list):
            favoritos = []
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex),
            nome=str(d.get("nome", "Leitor")),
            bio=str(d.get("bio", "")),
            foto_path=str(d.get("foto_path", "")),
            favoritos=[str(f) for f in favoritos],
            criado_em=str(d.get("criado_em", "")),
        )

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class VolumeCatalogo:
    """Um volume (PDF) disponível no catálogo remoto.

    `url` aponta para o arquivo PDF. `tamanho_mb` é informativo (0 = desconhecido).
    """
    numero: int
    titulo: str
    url: str
    tamanho_mb: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "VolumeCatalogo":
        try:
            numero = int(d.get("numero", 1))
        except (TypeError, ValueError):
            numero = 1
        try:
            tamanho = float(d.get("tamanho_mb", 0.0))
        except (TypeError, ValueError):
            tamanho = 0.0
        return cls(
            numero=numero,
            titulo=str(d.get("titulo", f"Vol. {numero}")),
            url=str(d.get("url", "")),
            tamanho_mb=max(0.0, tamanho),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CatalogoItem:
    """Uma obra disponível para download no catálogo remoto.

    Não confundir com obra local (que é uma pasta em pdf_padrao/).
    Uma vira a outra quando o usuário baixa todos os volumes.
    """
    id: str
    nome: str
    autor: str = ""
    descricao: str = ""
    capa_url: str = ""
    volumes: List[VolumeCatalogo] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "CatalogoItem":
        volumes_brutos = d.get("volumes", [])
        volumes = [
            VolumeCatalogo.from_dict(v)
            for v in volumes_brutos if isinstance(v, dict)
        ]
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex),
            nome=str(d.get("nome", "")),
            autor=str(d.get("autor", "")),
            descricao=str(d.get("descricao", "")),
            capa_url=str(d.get("capa_url", "")),
            volumes=volumes,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        # volumes são dataclasses — precisam ser convertidos manualmente
        d["volumes"] = [v.to_dict() for v in self.volumes]
        return d