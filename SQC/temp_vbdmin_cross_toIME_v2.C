// 15×1 探针卡 vs 探针台 数据交叉校验
// 统一流程：先找全局最小 Vbd，再统一偏压测漏电流
// 文件中保存的vbdmin进行了温度校正
// Tianyuan Zhang, IHEP  tyzhang@ihep.ac.cn

#include <TH2.h>
#include <TGraph.h>
#include <TStyle.h>
#include <TCanvas.h>
#include <TGaxis.h>
#include <TText.h>
#include <TROOT.h>

#include <fstream>
#include <iostream>
#include <iomanip>
#include <cmath>   // 新增：支持 std::abs()

#define Sup 300        // 直方图电压上限
#define VBD 165        // 合格阈值电压

#define WAFER REPLACE_WAFERNUM
#define SENSOR REPLACE_SENSORNUM

TString out = "/mnt/d/HGTD/per_pad_2nd/B36/W3_P2/";
TString addIME = "/mnt/d/HGTD/2nd/20WS0013600003/20WS2036000302-%d.csv"; //ProbeCard IME
TString addIHEP = "/mnt/d/HGTD/B36/W3_P2/SweepVoltage0/1-%d.csv"; //Needle IHEP Huairou

void temp_vbdmin_cross_toIME_v2()
{
    // ---------- 0. 存储 ----------
    const int NProbe = 15;
    const int NNeedle = 225;

    double ProbeVbd[NProbe + 1] = { 0 };   // 1..15
    double ProbeLKG[NProbe + 1] = { 0 };
    double NeedleVbd[NNeedle + 1] = { 0 };   // 1..225
    double NeedleLKG[NNeedle + 1] = { 0 };

    double ProbeVbdMin = 1e3;
    double ProbeVbdMin20d = 1e3;
    double ProbeVbdMax = 0;
    double ProbeLKGMin = 1;
    double ProbeLKGMax = 1e-11;
    double NeedleVbdMin = 1e3;
    double NeedleVbdMin20d = 1e3;
    double NeedleVbdMax = 0;
    double NeedleLKGMin = 1;
    double NeedleLKGMax = 1e-10;
    double hime[15] = { 0 };               // 15 列平均漏电流

    int validProbe = 0, validNeedle = 0;

    double Tp;
    std::cout << "请输入探卡测试温度 (°C): ";
    std::cin >> Tp;
    double Tn;
    std::cout << "请输入探针测试温度 (°C): ";
    std::cin >> Tn;

    // ---------- 1. 第一轮：仅取 Vbd ----------
    // --- 探针卡 15 通道 ---
    for (int i = 1; i <= NProbe; ++i)
    {
        TGraph* g = new TGraph(Form(addIME, i), "%lg,%lg");
        int N = g->GetN();
        if (!N) { delete g; continue; }
        double* vx = g->GetX(); double* vy = g->GetY();
        for (int k = 0; k < N; ++k) { vx[k] = vx[k]; vy[k] = vy[k]; }
        double Vbd = Sup;
        double Vbd20d = Sup;
        for (int k = 0; k < N - 1; ++k) {
            if (vy[k] * 1e6 < 15 * 0.5 && vy[k + 1] * 1e6 > 15 * 0.5) {
                double vx1 = vx[k + 1], vx2 = vx[k];
                double vy1 = vy[k + 1], vy2 = vy[k];
                Vbd = vx2 + (vx1 - vx2) * (0.5 * 15 * 1e-6 - vy2) / (vy1 - vy2);
                Vbd20d = Vbd - (Tp - 20) * 1.1;
                break;
            }
        }
        if (Vbd20d >= 165 && Vbd20d <= 195) ++validProbe;
        ProbeVbd[i] = Vbd20d;
        ProbeVbdMin = TMath::Min(ProbeVbdMin, Vbd);
        ProbeVbdMin20d = TMath::Min(ProbeVbdMin20d, Vbd20d);
        delete g;
    }

    // --- 探针台 225 像素 ✅ 修改：取绝对值 + 读取第1列和第3列 ---
    for (int idx = 1; idx <= NNeedle; ++idx)
    {
        TGraph* g = new TGraph(Form(addIHEP, idx), "%lg,%*lg,%lg");
        int N = g->GetN();
        if (!N) { delete g; continue; }
        double* vx = g->GetX(); double* vy = g->GetY();
        for (int k = 0; k < N; ++k) {
            vx[k] = std::abs(vx[k]);   // ✅ 取绝对值
            vy[k] = std::abs(vy[k]);   // ✅ 取绝对值
        }
        double Vbd = Sup;
        double Vbd20d = Sup;
        for (int k = 0; k < N - 1; ++k) {
            if (vy[k] * 1e6 < 0.5 && vy[k + 1] * 1e6 > 0.5) {
                double vx1 = vx[k + 1], vx2 = vx[k];
                double vy1 = vy[k + 1], vy2 = vy[k];
                Vbd = vx2 + (vx1 - vx2) * (0.5 * 1e-6 - vy2) / (vy1 - vy2);
                Vbd20d = Vbd - (Tn - 20) * 1.1;
                break;
            }
        }
        if (Vbd20d >= 165 && Vbd20d <= 195) ++validNeedle;
        NeedleVbd[idx] = Vbd20d;
        //std::cout << "Pixel " << idx << ": Vbd20d = " << Vbd20d << " V" << std::endl;  //打印每个像素的电压
        NeedleVbdMin = TMath::Min(NeedleVbdMin, Vbd);
        NeedleVbdMin20d = TMath::Min(NeedleVbdMin20d, Vbd20d);
        delete g;
    }

    // ---------- 2. 第二轮：统一偏压测漏电流 ----------
    double VProbe = 0.8 * ProbeVbdMin;
    double VNeedle = 0.8 * NeedleVbdMin;

    // --- 探针卡 ---
    for (int i = 1; i <= NProbe; ++i)
    {
        TGraph* g = new TGraph(Form(addIME, i), "%lg,%lg");
        int N = g->GetN();
        if (!N) { delete g; continue; }
        double* vx = g->GetX(); double* vy = g->GetY();
        for (int k = 0; k < N; ++k) { vx[k] = vx[k]; vy[k] = vy[k]; }
        double lkg = 0;
        for (int k = 0; k < N - 1; ++k) {
            if (vx[k] < VProbe && vx[k + 1] > VProbe) {
                double vx1 = vx[k + 1], vx2 = vx[k];
                double vy1 = vy[k + 1], vy2 = vy[k];
                lkg = vy2 + (vy1 - vy2) * (VProbe - vx2) / (vx1 - vx2);
                break;
            }
        }
        ProbeLKG[i] = lkg;
        ProbeLKGMin = TMath::Min(ProbeLKGMin, lkg);
        ProbeLKGMax = TMath::Max(ProbeLKGMax, lkg);
        delete g;
    }

    // --- 探针台 ✅ 修改：取绝对值 + 读取第1列和第3列 ---
    for (int idx = 1; idx <= NNeedle; ++idx)
    {
        TGraph* g = new TGraph(Form(addIHEP, idx), "%lg,%*lg,%lg");
        int N = g->GetN();
        if (!N) { delete g; continue; }
        double* vx = g->GetX(); double* vy = g->GetY();
        for (int k = 0; k < N; ++k) {
            vx[k] = std::abs(vx[k]);   // ✅ 取绝对值
            vy[k] = std::abs(vy[k]);   // ✅ 取绝对值
        }
        double lkg = 0;
        for (int k = 0; k < N - 1; ++k) {
            if (vx[k] < VNeedle && vx[k + 1] > VNeedle) {
                double vx1 = vx[k + 1], vx2 = vx[k];
                double vy1 = vy[k + 1], vy2 = vy[k];
                lkg = vy2 + (vy1 - vy2) * (VNeedle - vx2) / (vx1 - vx2);
                break;
            }
        }
        NeedleLKG[idx] = lkg;
        NeedleLKGMin = TMath::Min(NeedleLKGMin, lkg);
        NeedleLKGMax = TMath::Max(NeedleLKGMax, lkg);

        // 15 列平均
        int col = (idx - 1) % 15;
        hime[col] += lkg;
        delete g;
    }
    double IProbe = ProbeLKGMin;
    double INeedle = NeedleLKGMin;
    // 归一化列平均
    for (int c = 0; c < 15; ++c) hime[c] /= 15;

    // ---------- 3. 绘图 ----------
    TCanvas* c00 = new TCanvas("c00", "VMap", 1000, 500);
    gPad->SetGridx(1);
    gPad->SetGridy(1);
    c00->SetRightMargin(0.17);
    TH2D* hV = new TH2D("hV", ";X;Y;V_{BD} [V]", 31, 0, 31, 15, 0, 15);
    hV->SetContour(30);
    hV->GetZaxis()->SetRangeUser(0, Sup);
    hV->GetXaxis()->SetRange(1, 31);
    hV->GetXaxis()->SetNdivisions(-31);
    hV->GetXaxis()->SetLabelFont(42);
    hV->GetXaxis()->SetTitleOffset(1);
    hV->GetXaxis()->SetTitleFont(42);
    hV->GetXaxis()->SetLabelSize(0);
    hV->GetYaxis()->SetLabelSize(0);
    hV->GetYaxis()->SetRange(1, 15);
    hV->GetYaxis()->SetNdivisions(-15);
    hV->GetYaxis()->SetLabelFont(42);
    hV->GetYaxis()->SetTitleFont(42);
    hV->GetZaxis()->SetLabelFont(42);
    hV->GetZaxis()->SetTitleOffset(1.5);
    hV->GetZaxis()->SetTitleFont(42);
    hV->GetZaxis()->SetRangeUser(0, Sup);
    hV->SetStats(kFALSE);
    for (int i = 1; i <= 15; ++i) {
        for (int r = 1; r <= 15; ++r) hV->Fill(i - 0.5, r - 0.5, ProbeVbd[i]);
    }
    for (int idx = 1; idx <= 225; ++idx) {
        int col = (idx - 1) % 15 + 1;
        int row = 15 - (idx - 1) / 15;
        hV->Fill(col + 15.5 - 0.5, row - 0.5, NeedleVbd[idx]);
    }
    hV->Draw("COLZ");
    // 1. 探针卡 15×15
    TLatex* txt = new TLatex();
    txt->SetTextSize(0.02);
    txt->SetTextAlign(22);

    for (int i = 1; i <= 15; ++i) {
        double row = 7.5;
        txt->DrawLatex(i - 0.5, row, Form("%.0f", ProbeVbd[i]));
    }

    // 2. 探针台 15×15
    for (int idx = 1; idx <= 225; ++idx) {
        int col = (idx - 1) % 15 + 1;
        int row = 15 - (idx - 1) / 15;
        txt->DrawLatex(col + 15.5, row - 0.5, Form("%.0f", NeedleVbd[idx]));
    }
    TText* ProbeCard = new TText(6.5, 15.5, "ProbeCard");
    ProbeCard->SetTextFont(23);
    ProbeCard->SetTextSize(35);
    ProbeCard->SetTextAngle(0);
    ProbeCard->Draw();
    TText* Needle = new TText(22.5, 15.5, "Needle");
    Needle->SetTextFont(23);
    Needle->SetTextSize(35);
    Needle->SetTextAngle(0);
    Needle->Draw();
    TText* Sensor = new TText(15.5, -1.3, "Sensor");
    Sensor->SetTextFont(23);
    Sensor->SetTextSize(35);
    Sensor->SetTextAngle(0);
    Sensor->SetTextAlign(22);
    Sensor->Draw();
    hV->SetTitle(" ; ; ;V_{BD} (V)");
    hV->GetZaxis()->SetLabelOffset(0.01);
    c00->SaveAs(out + "VMap_Sensor.pdf");
    c00->SaveAs(out + "VMap_Sensor.png");

    TCanvas* c11 = new TCanvas("c11", "IMap", 1000, 500);
    c11->SetRightMargin(0.17);
    TH2D* hI = new TH2D("hI", ";X;Y;I_{leak} @ 0.8VbdMin [A]", 31, 0, 31, 15, 0, 15);
    hI->SetContour(30);
    hI->GetZaxis()->SetRangeUser(1e-9, 1e-7);
    hI->GetZaxis()->SetNdivisions(-3010);
    hI->GetXaxis()->SetRange(1, 31);
    hI->GetXaxis()->SetNdivisions(-31);
    hI->GetXaxis()->SetLabelFont(42);
    hI->GetXaxis()->SetTitleOffset(1);
    hI->GetXaxis()->SetTitleFont(42);
    hI->GetXaxis()->SetLabelSize(0);
    hI->GetYaxis()->SetLabelSize(0);
    hI->GetYaxis()->SetRange(1, 15);
    hI->GetYaxis()->SetNdivisions(-15);
    hI->GetYaxis()->SetLabelFont(42);
    hI->GetYaxis()->SetTitleFont(42);
    hI->GetZaxis()->SetLabelFont(42);
    hI->GetZaxis()->SetTitleOffset(1.5);
    hI->GetZaxis()->SetTitleFont(42);
    hI->SetStats(kFALSE);
    for (int i = 1; i <= 15; ++i) {
        for (int r = 1; r <= 15; ++r) hI->Fill(i - 0.5, r - 0.5, ProbeLKG[i] / 15);
    }
    for (int idx = 1; idx <= 225; ++idx) {
        int col = (idx - 1) % 15 + 1;
        int row = 15 - (idx - 1) / 15;
        hI->Fill(col + 15.5 - 0.5, row - 0.5, NeedleLKG[idx]);
    }
    c11->cd(1);
    gPad->SetGridx(1);
    gPad->SetGridy(1);
    gPad->SetLogz();
    hI->Draw("COLZ");
    // 1. 探针卡 15×15
    txt->SetTextSize(0.023);
    txt->SetTextAlign(22);

    for (int i = 1; i <= 15; ++i) {
        double row = 7.5;
        txt->DrawLatex(i - 0.5, row, Form("%.1f", ProbeLKG[i] / 15 * 1e9));
    }

    // 2. 探针台 15×15
    for (int idx = 1; idx <= 225; ++idx) {
        int col = (idx - 1) % 15 + 1;
        int row = 15 - (idx - 1) / 15;
        txt->DrawLatex(col + 15.5, row - 0.5, Form("%.1f", NeedleLKG[idx] * 1e9));
    }
    // 放在 hV->Draw("COLZ"); 或 hI->Draw("COLZ"); 之后
    TLatex* note = new TLatex();
    note->SetNDC();
    note->SetTextSize(0.03);
    note->SetTextFont(42);
    note->DrawLatex(0.05, 0.96, "Values * 1e9 on the grid");
    ProbeCard->SetTextFont(23);
    ProbeCard->SetTextSize(35);
    ProbeCard->Draw();

    Needle->SetTextFont(23);
    Needle->SetTextSize(35);
    Needle->Draw();

    Sensor->SetTextFont(23);
    Sensor->SetTextSize(35);
    Sensor->SetTextAlign(22);
    Sensor->Draw();

    hI->SetTitle(" ; ; ;Leakage Current (A)");
    hI->GetZaxis()->SetLabelOffset(0.01);

    c11->SaveAs(out + "IMap_Sensor.pdf");
    c11->SaveAs(out + "IMap_Sensor.png");
    // 直方图
    TCanvas* c1 = new TCanvas("c1", "", 1000, 500);
    c1->Divide(2, 1);
    TH1F* hBVProbe = new TH1F("hBVProbe", "ProbeCard BV", 40, 0, Sup);
    TH1F* hBVNeedle = new TH1F("hBVNeedle", "Needle BV", 40, 0, Sup);
    for (int i = 1; i <= 15; ++i) { hBVProbe->Fill(ProbeVbd[i]); }
    c1->cd(1);
    hBVProbe->Draw();
    for (int idx = 1; idx <= 225; ++idx) { hBVNeedle->Fill(NeedleVbd[idx]); }
    c1->cd(2);
    hBVNeedle->Draw();
    c1->SaveAs(out + "BVHist_Sensor.png");

    TCanvas* c2 = new TCanvas("c2", "", 1200, 600);
    c2->Divide(2, 1);
    TH1F* hILProbe = new TH1F("hILProbe", "ProbeCard I@0.8VbdMin", 200, 0, 1e-6);
    TH1F* hILNeedle = new TH1F("hILNeedle", "Needle I@0.8VbdMin", 200, 0, 1e-6);
    for (int i = 1; i <= 15; ++i) { hILProbe->Fill(ProbeLKG[i]); }
    for (int idx = 1; idx <= 225; ++idx) { hILNeedle->Fill(NeedleLKG[idx]); }
    c2->cd(1); hILProbe->Draw();
    c2->cd(2); hILNeedle->Draw();
    c2->SaveAs(out + "IHist_Sensor.png");

    // 列平均
    TCanvas* c3 = new TCanvas("c3", "", 800, 600);
    TH1F* hCol = new TH1F("hCol", "Average I per column @ 0.8VbdMin", 15, 0.5, 15.5);
    for (int c = 0; c < 15; ++c) hCol->SetBinContent(c + 1, hime[c]);
    hCol->Draw();
    c3->SaveAs(out + "ColumnAvg_Sensor.png");

    TCanvas* c4 = new TCanvas("c4", "IV Curve", 2000, 1000);
    c4->Divide(2, 1);
    gPad->SetRightMargin(0.15);

    // --- ProbeCard IV (正数，保持不变) ---
    c4->cd(1);
    gPad->SetLogy(1);
    gPad->DrawFrame(0., 1e-10, 260, 5e-5);
    for (int i = 1; i < 16; i++) {
        TGraph* g11 = new TGraph(Form(addIME, i), "%lg,%lg");
        g11->Draw("same");
        g11->SetLineColor(3 + i);
        g11->SetTitle(" ; ;Bias (V) ;Leakage Current (A)");
    }
    TText* IMEI = new TText(100, 5.3E-5, "ProbeCard");
    IMEI->SetTextFont(23);
    IMEI->SetTextSize(35);
    IMEI->SetTextAngle(0);
    IMEI->Draw();

    // --- Needle IV (负数，取绝对值) ✅ 修改 ---
    c4->cd(2);
    gPad->SetLogy(1);
    gPad->DrawFrame(0., 1e-11, 260, 5e-5);
    for (int j = 1; j <= 225; ++j) {
        if (j % 15 == 0 || (j - 1) % 15 == 0) continue;
        if (j <= 15 || j >= 210) continue;
        TGraph* g1 = new TGraph(Form(addIHEP, j), "%lg,%*lg,%lg");
        int N = g1->GetN();
        double* vx = g1->GetX();
        double* vy = g1->GetY();
        for (int k = 0; k < N; ++k) {
            vx[k] = std::abs(vx[k]);   // ✅ 取绝对值（负数转正）
            vy[k] = std::abs(vy[k]);   // ✅ 取绝对值（负数转正）
        }
        g1->Draw("same L");
        g1->SetLineColor((j - 1) % 15 + 2);
        g1->SetTitle(" ;Bias (V) ;Leakage Current (A)");
    }
    TText* IHEPI = new TText(100, 5.3E-5, "Needle");
    IHEPI->SetTextFont(23);
    IHEPI->SetTextSize(35);
    IHEPI->SetTextAngle(0);
    IHEPI->Draw();

    c4->SaveAs(out + "IVCurve_Sensor.pdf");
    c4->SaveAs(out + "IVCurve_Sensor.png");

    // ---------- 4. 打印汇总 ----------
    std::cout << "ProbeCard  Vbd min = " << ProbeVbdMin20d << std::endl;
    std::cout << "Needle     Vbd min = " << NeedleVbdMin20d << std::endl;
    std::cout << "Valid  ProbeCard = " << validProbe << "/" << NProbe << std::endl;
    std::cout << "Valid  Needle    = " << validNeedle << "/" << NNeedle << std::endl;

    // ---------- 5. 计算并保存 Vbd 统计量 ----------
    TH1F* hProbe = new TH1F("hProbe", "ProbeCard Vbd;Vbd [V];Counts", 100, 0, Sup);
    TH1F* hNeedle = new TH1F("hNeedle", "Needle Vbd;Vbd [V];Counts", 100, 0, Sup);
    for (int i = 1; i <= 15; ++i) hProbe->Fill(ProbeVbd[i]);
    double meanProbe = hProbe->GetMean();
    double rmsProbe = hProbe->GetRMS();
    for (int idx = 1; idx <= 225; ++idx) hNeedle->Fill(NeedleVbd[idx]);
    double meanNeedle = hNeedle->GetMean();
    double rmsNeedle = hNeedle->GetRMS();

    // 内圈 Needle LKG 最大/最小
    double innerMax = 1e-11, innerMin = 1e4;
    for (int idx = 1; idx <= 225; ++idx) {
        int col = (idx - 1) % 15 + 1;
        int row = 15 - (idx - 1) / 15;
        if (col == 1 || col == 15 || row == 1 || row == 15) continue;
        innerMax = TMath::Max(innerMax, NeedleLKG[idx]);
        innerMin = TMath::Min(innerMin, NeedleLKG[idx]);
    }
    double innerIRatio = (innerMin <= 0) ? 0 : innerMax / innerMin;
    //次内圈 Needle LKG 最大/最小
    double inner2Max = 1e-11, inner2Min = 1e4;
    for (int idx = 1; idx <= 225; ++idx) {
        int col = (idx - 1) % 15 + 1;
        int row = 15 - (idx - 1) / 15;
        if (col == 1 || col == 15 || row == 1 || row == 15 || col == 2 || col == 14 || row == 2 || row == 14) continue;
        inner2Max = TMath::Max(inner2Max, NeedleLKG[idx]);
        inner2Min = TMath::Min(inner2Min, NeedleLKG[idx]);
    }
    double inner2IRatio = (inner2Min <= 0) ? 0 : inner2Max / inner2Min;

    double ProbeIRatio = ProbeLKGMax / ProbeLKGMin;
    double NeedleLKGIRatio = NeedleLKGMax / NeedleLKGMin;
    std::ofstream csv(out + "crosscheck.csv");
    csv << "Group,Mean,RMS,VbdMin,RMS/Mean,IRatio,LKGMin,LKGMax,Valid\n";

    // --- 探针卡 15 通道 ---
    csv << "ProbeCard,"
        << std::fixed << std::setprecision(2) << meanProbe << ","
        << std::fixed << std::setprecision(2) << rmsProbe << ","
        << std::fixed << std::setprecision(2) << ProbeVbdMin20d << ","
        << std::fixed << std::setprecision(2) << (rmsProbe / meanProbe * 100) << "%,"
        << std::fixed << std::setprecision(2) << ProbeIRatio << ","
        << std::scientific << std::setprecision(2) << ProbeLKGMin << ","
        << std::scientific << std::setprecision(2) << ProbeLKGMax << ","
        << validProbe << "\n";

    // --- 探针台 225 像素 ---
    csv << "Needle,"
        << std::fixed << std::setprecision(2) << meanNeedle << ","
        << std::fixed << std::setprecision(2) << rmsNeedle << ","
        << std::fixed << std::setprecision(2) << NeedleVbdMin20d << ","
        << std::fixed << std::setprecision(2) << (rmsNeedle / meanNeedle * 100) << "%,"
        << std::fixed << std::setprecision(2) << NeedleLKGIRatio << ","
        << std::scientific << std::setprecision(2) << NeedleLKGMin << ","
        << std::scientific << std::setprecision(2) << NeedleLKGMax << ","
        << validNeedle << "\n";

    csv << "Needle(inner),"
        << std::fixed << std::setprecision(2) << meanNeedle << ","
        << std::fixed << std::setprecision(2) << rmsNeedle << ","
        << std::fixed << std::setprecision(2) << NeedleVbdMin20d << ","
        << std::fixed << std::setprecision(2) << (rmsNeedle / meanNeedle * 100) << "%,"
        << std::fixed << std::setprecision(2) << innerIRatio << ","
        << std::scientific << std::setprecision(2) << innerMin << ","
        << std::scientific << std::setprecision(2) << innerMax << ","
        << validNeedle << "\n";

    csv << "Needle(inner2),"
        << std::fixed << std::setprecision(2) << meanNeedle << ","
        << std::fixed << std::setprecision(2) << rmsNeedle << ","
        << std::fixed << std::setprecision(2) << NeedleVbdMin20d << ","
        << std::fixed << std::setprecision(2) << (rmsNeedle / meanNeedle * 100) << "%,"
        << std::fixed << std::setprecision(2) << inner2IRatio << ","
        << std::scientific << std::setprecision(2) << inner2Min << ","
        << std::scientific << std::setprecision(2) << inner2Max << ","
        << validNeedle << "\n";

    csv.close();
    std::cout << "CSV saved: crosscheck.csv" << std::endl;
}
