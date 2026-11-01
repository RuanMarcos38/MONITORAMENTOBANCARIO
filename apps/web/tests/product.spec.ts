import { test, expect, Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

async function login(page: Page, who = 'analyst') {
  await page.goto('/');
  await page.getByLabel('E-mail', { exact: true }).fill(who + '@example.test');
  await page.getByLabel('Senha', { exact: true }).fill('isolated-e2e-test-password-2026');
  await page.getByRole('button', { name: 'Acessar com segurança' }).click();
  await expect(page.getByRole('heading', { name: 'Visão Geral', exact: true })).toBeVisible();
}

async function navigate(page: Page, title: string) {
  await expect(page.getByRole('button', {name:'Atualizar painel',exact:true})).toBeVisible();
  const menu = page.getByRole('button', { name: 'Abrir menu', exact: true });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole('navigation').getByRole('button', { name: title, exact: true }).click();
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
}

test('importar, revisar alerta, investigar com documento e exportar PDF', async ({ page }) => {
  await login(page);
  await page.locator('input[type=file]').setInputFiles({name:'extrato.csv',mimeType:'text/csv',buffer:Buffer.from('id,date,amount,beneficiary\ne2e-1,2026-10-01,100.00,Empresa de teste isolada\ne2e-2,2026-10-01,100.00,Empresa de teste isolada\n')});
  await navigate(page, 'Alertas');
  const row = page.getByRole('row').filter({hasText:'Inconsistência transacional para revisão'});
  await expect(row).toBeVisible();
  await row.getByRole('button', {name:'Abrir',exact:true}).click();
  const form = page.locator('form').filter({has:page.getByRole('heading',{name:'Abrir investigação deste alerta',exact:true})});
  await form.getByLabel('Título do caso', {exact:true}).fill('Caso E2E documental');
  await form.getByLabel('Objetivo e fundamento', {exact:true}).fill('Revisar documentos de teste isolados e rastreáveis.');
  await form.getByRole('button',{name:'Salvar',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Registro salvo.'})).toBeVisible();
  await navigate(page, 'Central de Investigação');
  const caseRow = page.getByRole('row').filter({hasText:'Caso E2E documental'});
  await caseRow.getByRole('button',{name:'Abrir',exact:true}).click();
  await page.locator('input[type=file]').setInputFiles({name:'evidencia.txt',mimeType:'text/plain',buffer:Buffer.from('Documento sintético restrito ao teste E2E.')});
  await expect(page.getByRole('link').filter({hasText:'evidencia.txt'})).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Baixar dossiê PDF',exact:true}).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect((await readFile(path!)).subarray(0,5).toString()).toBe('%PDF-');
  await page.getByRole('button',{name:'Sair da plataforma',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Bem-vindo de volta'})).toBeVisible();
});

test('criar caso no celular e preservar após recarregar', async ({ page }) => {
  await page.setViewportSize({width:375,height:667});
  await login(page);
  await navigate(page,'Central de Investigação');
  const form = page.locator('form').filter({has:page.getByRole('heading',{name:'Abrir investigação',exact:true})});
  await form.getByLabel('Título do caso',{exact:true}).fill('Caso mobile independente');
  await form.getByLabel('Objetivo e fundamento',{exact:true}).fill('Validar persistência e navegação móvel em ambiente de teste.');
  await form.getByRole('button',{name:'Salvar',exact:true}).click();
  await expect(page.getByRole('row').filter({hasText:'Caso mobile independente'})).toBeVisible();
  await page.reload();
  await navigate(page,'Central de Investigação');
  await expect(page.getByRole('row').filter({hasText:'Caso mobile independente'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test('visualizador de outra organização não acessa caso privado nem grava dados', async ({ page }) => {
  await login(page,'viewer');
  await navigate(page,'Central de Investigação');
  await expect(page.getByText('Confidencial CI Alpha',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Abrir investigação',exact:true})).toHaveCount(0);
  const response = await page.request.post('/api/v1/investigations',{data:{title:'Tentativa não autorizada',note:'Não deve criar este registro.'}});
  expect(response.status()).toBe(403);
});

