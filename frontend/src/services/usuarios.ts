import { chamar } from "./api";
import type {
  Cargo,
  Papel,
  SenhaRedefinida,
  UsuarioCriado,
  UsuarioResumo,
} from "@/types/auth";

export const listarUsuarios = () => chamar<UsuarioResumo[]>("/usuarios");

export const criarUsuario = (dados: {
  usuario: string;
  email: string;
  nome_exibicao: string;
  papel: Papel;
  cargo: Cargo;
}) =>
  chamar<UsuarioCriado>("/usuarios", {
    method: "POST",
    body: JSON.stringify(dados),
    headers: { "Content-Type": "application/json" },
  });

/** Gera senha provisória de uso único. O gestor nunca escolhe a senha:
 *  se escolhesse, passaria a saber a senha da pessoa. */
export const redefinirSenha = (id: number) =>
  chamar<SenhaRedefinida>(`/usuarios/${id}/senha`, { method: "POST" });

const alterar = <T>(id: number, campo: string, corpo: unknown) =>
  chamar<T>(`/usuarios/${id}/${campo}`, {
    method: "PATCH",
    body: JSON.stringify(corpo),
    headers: { "Content-Type": "application/json" },
  });

/** Nome de exibição e e-mail. O nome de usuário é imutável. */
export const alterarDados = (id: number, dados: { nome_exibicao: string; email: string }) =>
  alterar<UsuarioResumo>(id, "dados", dados);

export const alterarPapel = (id: number, papel: Papel) =>
  alterar<UsuarioResumo>(id, "papel", { papel });

export const alterarCargo = (id: number, cargo: Cargo) =>
  alterar<UsuarioResumo>(id, "cargo", { cargo });

export const definirSituacao = (id: number, ativo: boolean) =>
  alterar<UsuarioResumo>(id, "situacao", { ativo });

/** As empresas que a pessoa alcança — e todas as outras, para conceder. */
export interface AcessoAEmpresa {
  empresa_id: number;
  razao_social: string;
  uf: string | null;
  tem_acesso: boolean;
  desde: string | null;
}

export const lerAcessoAEmpresas = (id: number) =>
  chamar<AcessoAEmpresa[]>(`/usuarios/${id}/empresas`);

/** Faz o acesso ser exatamente esta lista. Tirar não apaga a alocação:
 *  encerra, para o histórico continuar respondível. */
export const definirAcessoAEmpresas = (id: number, empresas: number[]) =>
  chamar<{ concedidas: string[]; encerradas: string[] }>(
    `/usuarios/${id}/empresas`,
    {
      method: "PUT",
      body: JSON.stringify({ empresas }),
      headers: { "Content-Type": "application/json" },
    },
  );

export const desbloquear = (id: number) =>
  chamar<UsuarioResumo>(`/usuarios/${id}/desbloquear`, { method: "POST" });

/** Único caminho para sair da senha provisória. */
export const trocarPropriaSenha = (senha_atual: string, senha_nova: string) =>
  chamar<void>("/usuarios/eu/senha", {
    method: "POST",
    body: JSON.stringify({ senha_atual, senha_nova }),
    headers: { "Content-Type": "application/json" },
  });
