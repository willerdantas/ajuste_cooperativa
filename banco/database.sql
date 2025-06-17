-- Tabela de Usuários
DROP TABLE IF EXISTS usuario;
CREATE TABLE usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    login TEXT NOT NULL UNIQUE,
    senha TEXT NOT NULL,
    perfil TEXT NOT NULL,
    cooperativas TEXT, -- IDs das cooperativas separados por vírgula (para múltiplas associações)
    ativo INTEGER DEFAULT 1
);

-- Tabela de Cooperativas
DROP TABLE IF EXISTS cooperativa;
CREATE TABLE cooperativa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razao_social TEXT NOT NULL,
    nome_fantasia TEXT NOT NULL,
    cnpj TEXT NOT NULL,
    endereco TEXT NOT NULL,
    telefone TEXT NOT NULL,
    email TEXT NOT NULL,
    categoria TEXT NOT NULL,
    logo TEXT,
    data_inicio INTEGER, -- Dia de início do período de faturamento
    data_fim INTEGER     -- Dia de fim do período de faturamento
);

-- Tabela de Profissionais
DROP TABLE IF EXISTS profissional;
CREATE TABLE profissional (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_completo TEXT NOT NULL,
    matricula TEXT NOT NULL UNIQUE,
    celular TEXT,
    email TEXT,
    cooperativa_id INTEGER NOT NULL,
    categoria_id INTEGER NOT NULL,
    FOREIGN KEY (cooperativa_id) REFERENCES cooperativa(id),
    FOREIGN KEY (categoria_id) REFERENCES categoria_profissional(id)
);

-- Tabela de Categorias Profissionais
DROP TABLE IF EXISTS categoria_profissional;
CREATE TABLE categoria_profissional (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL
);

-- Tabela de relação Cooperativa <-> Categoria Profissional (muitos para muitos)
DROP TABLE IF EXISTS cooperativa_categoria;
CREATE TABLE cooperativa_categoria (
    cooperativa_id INTEGER,
    categoria_id INTEGER,
    FOREIGN KEY (cooperativa_id) REFERENCES cooperativa(id),
    FOREIGN KEY (categoria_id) REFERENCES categoria_profissional(id),
    PRIMARY KEY (cooperativa_id, categoria_id)
);

-- Tabela de Períodos de Folha de Pagamento
DROP TABLE IF EXISTS periodo_folha;
CREATE TABLE periodo_folha (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cooperativa_id INTEGER,
    descricao TEXT NOT NULL,
    data_inicio DATE NOT NULL,
    data_fim DATE NOT NULL,
    FOREIGN KEY (cooperativa_id) REFERENCES cooperativa(id)
);

-- Tabela de Justificativas
DROP TABLE IF EXISTS justificativa;
CREATE TABLE justificativa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cooperativa_id INTEGER,
    profissional_id INTEGER,
    categoria_profissional TEXT,
    datahora_preenchimento TEXT,
    data_ocorrencia TEXT CHECK (data_ocorrencia LIKE '__/__/____'), -- Ensure format dd/mm/aaaa
    inicio_plantao TEXT,
    fim_plantao TEXT,
    justificativa TEXT,
    ocorrencia_arquivo TEXT,
    autorizacao INTEGER,
    justificativa_negada TEXT,
    ajuste_datahora TEXT,
    FOREIGN KEY (cooperativa_id) REFERENCES cooperativa(id),
    FOREIGN KEY (profissional_id) REFERENCES profissional(id)
);