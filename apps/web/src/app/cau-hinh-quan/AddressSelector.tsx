"use client";

import { useEffect, useState, useMemo } from "react";
import { apiGet } from "../../lib/api";
import { Field, Input, Select, Btn, Alert } from "../../ui/kit";
import { Icon } from "../../ui/icons";

export type AddressData = {
  dia_chi: string;
  dia_chi_chi_tiet: string;
  phuong_xa: string;
  phuong_xa_code: string;
  quan_huyen: string;
  quan_huyen_code: string;
  tinh: string;
  tinh_code: string;
  thanh_pho: string;
  google_maps_url?: string;
};

type Province = { code: number; name: string; division_type?: string };
type District = { code: number; name: string; province_code: number; division_type?: string };
type Ward = { code: number; name: string; district_code: number; division_type?: string };

interface AddressSelectorProps {
  data: AddressData;
  onChange: (patch: Partial<AddressData>) => void;
}

export function AddressSelector({ data, onChange }: AddressSelectorProps) {
  const [provinces, setProvinces] = useState<Province[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [wards, setWards] = useState<Ward[]>([]);

  const [loadingProvinces, setLoadingProvinces] = useState(false);
  const [loadingDistricts, setLoadingDistricts] = useState(false);
  const [loadingWards, setLoadingWards] = useState(false);
  const [fetchError, setFetchError] = useState("");
  const [copied, setCopied] = useState(false);

  // Tải danh sách 63 tỉnh/thành phố từ Address API
  useEffect(() => {
    let active = true;
    setLoadingProvinces(true);
    apiGet<Province[]>("/api/v1/geo/provinces")
      .then((res) => {
        if (active && Array.isArray(res)) {
          setProvinces(res);
        }
      })
      .catch((err) => {
        if (active) {
          setFetchError("Không thể tải danh mục tỉnh/thành từ API địa chỉ.");
        }
      })
      .finally(() => {
        if (active) setLoadingProvinces(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // Tải quận/huyện khi tinh_code thay đổi
  useEffect(() => {
    if (!data.tinh_code) {
      setDistricts([]);
      return;
    }
    let active = true;
    setLoadingDistricts(true);
    apiGet<District[]>(`/api/v1/geo/districts/${data.tinh_code}`)
      .then((res) => {
        if (active && Array.isArray(res)) {
          setDistricts(res);
        }
      })
      .catch(() => {
        if (active) setDistricts([]);
      })
      .finally(() => {
        if (active) setLoadingDistricts(false);
      });
    return () => {
      active = false;
    };
  }, [data.tinh_code]);

  // Tải phường/xã khi quan_huyen_code thay đổi
  useEffect(() => {
    if (!data.quan_huyen_code) {
      setWards([]);
      return;
    }
    let active = true;
    setLoadingWards(true);
    apiGet<Ward[]>(`/api/v1/geo/wards/${data.quan_huyen_code}`)
      .then((res) => {
        if (active && Array.isArray(res)) {
          setWards(res);
        }
      })
      .catch(() => {
        if (active) setWards([]);
      })
      .finally(() => {
        if (active) setLoadingWards(false);
      });
    return () => {
      active = false;
    };
  }, [data.quan_huyen_code]);

  // Sinh chuỗi địa chỉ đầy đủ chuẩn hóa
  const generatedAddress = useMemo(() => {
    const parts = [
      data.dia_chi_chi_tiet?.trim(),
      data.phuong_xa?.trim(),
      data.quan_huyen?.trim(),
      data.tinh?.trim(),
    ].filter(Boolean);
    return parts.join(", ");
  }, [data.dia_chi_chi_tiet, data.phuong_xa, data.quan_huyen, data.tinh]);

  function handleProvinceChange(codeStr: string) {
    const code = Number(codeStr);
    const sel = provinces.find((p) => p.code === code);
    const name = sel ? sel.name : "";
    const patch: Partial<AddressData> = {
      tinh: name,
      tinh_code: codeStr,
      quan_huyen: "",
      quan_huyen_code: "",
      phuong_xa: "",
      phuong_xa_code: "",
      thanh_pho: name, // Giữ tương thích ngược với API thời tiết cũ
    };

    // Tự động cập nhật dia_chi
    const parts = [data.dia_chi_chi_tiet?.trim(), name].filter(Boolean);
    if (parts.length > 0) {
      patch.dia_chi = parts.join(", ");
    }
    onChange(patch);
  }

  function handleDistrictChange(codeStr: string) {
    const code = Number(codeStr);
    const sel = districts.find((d) => d.code === code);
    const name = sel ? sel.name : "";
    const patch: Partial<AddressData> = {
      quan_huyen: name,
      quan_huyen_code: codeStr,
      phuong_xa: "",
      phuong_xa_code: "",
      thanh_pho: name || data.tinh,
    };

    const parts = [data.dia_chi_chi_tiet?.trim(), name, data.tinh?.trim()].filter(Boolean);
    if (parts.length > 0) {
      patch.dia_chi = parts.join(", ");
    }
    onChange(patch);
  }

  function handleWardChange(codeStr: string) {
    const code = Number(codeStr);
    const sel = wards.find((w) => w.code === code);
    const name = sel ? sel.name : "";
    const patch: Partial<AddressData> = {
      phuong_xa: name,
      phuong_xa_code: codeStr,
    };

    const parts = [
      data.dia_chi_chi_tiet?.trim(),
      name,
      data.quan_huyen?.trim(),
      data.tinh?.trim(),
    ].filter(Boolean);
    if (parts.length > 0) {
      patch.dia_chi = parts.join(", ");
    }
    onChange(patch);
  }

  function handleDetailChange(val: string) {
    const parts = [val.trim(), data.phuong_xa?.trim(), data.quan_huyen?.trim(), data.tinh?.trim()].filter(Boolean);
    onChange({
      dia_chi_chi_tiet: val,
      dia_chi: parts.length > 0 ? parts.join(", ") : val,
    });
  }

  function copyAddress() {
    const textToCopy = data.dia_chi || generatedAddress;
    if (!textToCopy) return;
    void navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const mapSearchUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
    data.dia_chi || generatedAddress || "Việt Nam"
  )}`;

  return (
    <div className="space-y-4">
      {fetchError && (
        <Alert kind="err">
          {fetchError} Bạn vẫn có thể nhập địa chỉ thủ công bên dưới.
        </Alert>
      )}

      {/* Bộ chọn 3 cấp hành chính Việt Nam */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Field
          label="Tỉnh / Thành phố"
          hint={loadingProvinces ? "Đang tải danh mục…" : "Chuẩn 63 tỉnh thành Việt Nam"}
        >
          <Select
            value={data.tinh_code || ""}
            onChange={(e) => handleProvinceChange(e.target.value)}
            disabled={loadingProvinces}
          >
            <option value="">-- Chọn Tỉnh / Thành phố --</option>
            {provinces.map((p) => (
              <option key={p.code} value={String(p.code)}>
                {p.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Quận / Huyện / Thị xã"
          hint={
            loadingDistricts
              ? "Đang tải quận/huyện…"
              : !data.tinh_code
                ? "Vui lòng chọn Tỉnh/TP trước"
                : "Quận/huyện thuộc tỉnh"
          }
        >
          <Select
            value={data.quan_huyen_code || ""}
            onChange={(e) => handleDistrictChange(e.target.value)}
            disabled={!data.tinh_code || loadingDistricts}
          >
            <option value="">-- Chọn Quận / Huyện --</option>
            {districts.map((d) => (
              <option key={d.code} value={String(d.code)}>
                {d.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Phường / Xã / Thị trấn"
          hint={
            loadingWards
              ? "Đang tải phường/xã…"
              : !data.quan_huyen_code
                ? "Vui lòng chọn Quận/Huyện trước"
                : "Phường/xã trực thuộc"
          }
        >
          <Select
            value={data.phuong_xa_code || ""}
            onChange={(e) => handleWardChange(e.target.value)}
            disabled={!data.quan_huyen_code || loadingWards}
          >
            <option value="">-- Chọn Phường / Xã --</option>
            {wards.map((w) => (
              <option key={w.code} value={String(w.code)}>
                {w.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {/* Số nhà, tên đường chi tiết */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Số nhà, tên đường / Tòa nhà"
          hint="VD: 45 Nguyễn Huệ, Tầng 2 hoặc Hẻm 128 Lê Lợi"
        >
          <Input
            value={data.dia_chi_chi_tiet || ""}
            onChange={(e) => handleDetailChange(e.target.value)}
            placeholder="Nhập số nhà, tên đường, ngõ ngách..."
          />
        </Field>

        <Field
          label="Link Google Maps (tùy chọn)"
          hint="Khách bấm vào link sẽ mở bản đồ chỉ đường thẳng tới quán"
        >
          <Input
            value={data.google_maps_url || ""}
            onChange={(e) => onChange({ google_maps_url: e.target.value })}
            placeholder="VD: https://maps.app.goo.gl/..."
          />
        </Field>
      </div>

      {/* Địa chỉ tổng hợp hoàn chỉnh */}
      <Field
        label="Địa chỉ hoàn chỉnh (Bot AI sẽ đọc và gửi cho khách)"
        hint="Tự động ghép từ bộ chọn trên. Bạn có thể sửa trực tiếp nếu muốn thêm ghi chú vị trí."
      >
        <div className="space-y-2">
          <Input
            value={data.dia_chi || ""}
            onChange={(e) => onChange({ dia_chi: e.target.value })}
            placeholder="VD: 45 Nguyễn Huệ, Phường Bến Nghé, Quận 1, Thành phố Hồ Chí Minh"
          />
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
            <div className="flex items-center gap-2 text-[var(--nq-muted)]">
              <span className="inline-flex items-center gap-1 rounded bg-[var(--nq-surface-hi)] px-2 py-0.5 font-mono text-[11px]">
                <Icon name="location" className="h-3 w-3 text-[var(--nq-copper)]" />
                {data.dia_chi ? "Đã định dạng chuẩn" : "Chưa có địa chỉ"}
              </span>
              {generatedAddress && data.dia_chi !== generatedAddress && (
                <button
                  type="button"
                  onClick={() => onChange({ dia_chi: generatedAddress })}
                  className="text-[var(--nq-copper)] hover:underline"
                >
                  (Khôi phục theo bộ chọn API)
                </button>
              )}
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={copyAddress}
                className="flex items-center gap-1 text-[var(--nq-muted)] hover:text-[var(--nq-fg)]"
              >
                <Icon name="clipboard" className="h-3.5 w-3.5" />
                <span>{copied ? "Đã chép!" : "Sao chép"}</span>
              </button>
              <a
                href={data.google_maps_url || mapSearchUrl}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-[var(--nq-copper)] hover:underline"
              >
                <Icon name="external-link" className="h-3.5 w-3.5" />
                <span>Xem trên Google Maps</span>
              </a>
            </div>
          </div>
        </div>
      </Field>
    </div>
  );
}
